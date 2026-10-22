package com.cornealai.backend.cases.importer;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.audit.AuditService;
import com.cornealai.backend.cases.SlitLampFindings;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.dto.CaseDtos.CaseDetails;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.CaseService;
import com.cornealai.backend.cases.service.DonorCaseService;
import jakarta.persistence.EntityManager;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.hibernate.Session;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * Bulk import of donor cases from CSV or Excel. A check (dry run) reports what every row would do;
 * the import applies the whole file in one transaction, and only if no row has an error. In "create"
 * mode existing tissue IDs are skipped; in "update" mode their details are updated with the row's
 * non-blank values (blank cells keep what the case has). Values are validated as on the Details form.
 */
@Service
public class CaseImportService {

    public enum Mode { CREATE, UPDATE }

    public record ImportRow(int row, String tissueId, String action, List<String> errors) {
    }

    public record ImportReport(boolean applied, String mode, int rows, int created, int updated, int skipped,
                               int withErrors, List<String> ignoredColumns, List<ImportRow> details) {
    }

    private record Planned(CaseImportFile.Row row, TissueNumber tissue, Optional<DonorCase> existing,
                           Map<String, String> values) {
    }

    /** Rows per JDBC batch when an import is written. */
    private static final int JDBC_BATCH_SIZE = 100;

    private final DonorCaseService donorCases;
    private final CaseService caseService;
    private final Validator validator;
    private final AuditService audit;
    private final EntityManager entityManager;

    public CaseImportService(DonorCaseService donorCases, CaseService caseService, Validator validator,
                             AuditService audit, EntityManager entityManager) {
        this.donorCases = donorCases;
        this.caseService = caseService;
        this.validator = validator;
        this.audit = audit;
        this.entityManager = entityManager;
    }

    public static Mode mode(String raw) {
        if (raw == null || raw.isBlank() || raw.equalsIgnoreCase("create")) {
            return Mode.CREATE;
        }
        if (raw.equalsIgnoreCase("update")) {
            return Mode.UPDATE;
        }
        throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "mode",
                "Mode must be \"create\" or \"update\".");
    }

    /** Checks the file and reports what each row would do; changes nothing. */
    public ImportReport check(String filename, byte[] data, Mode mode) {
        CaseImportFile.Parsed parsed = CaseImportFile.read(filename, data);
        return plan(parsed, mode, false, null);
    }

    /** Imports the file if every row is valid; otherwise changes nothing and returns the report with errors. */
    @Transactional
    public ImportReport apply(String filename, byte[] data, Mode mode, Long userId) {
        CaseImportFile.Parsed parsed = CaseImportFile.read(filename, data);
        return plan(parsed, mode, true, userId);
    }

    private ImportReport plan(CaseImportFile.Parsed parsed, Mode mode, boolean apply, Long userId) {
        List<ImportRow> results = new ArrayList<>();
        List<Planned> valid = new ArrayList<>();
        Map<String, Integer> firstRowOf = new HashMap<>();

        // Tissue IDs first, so the existing cases are found with one query rather than one per row.
        List<CaseImportFile.Row> rows = parsed.rows();
        List<TissueNumber> tissues = new ArrayList<>();
        List<List<String>> rowErrors = new ArrayList<>();
        for (CaseImportFile.Row row : rows) {
            List<String> errors = new ArrayList<>();
            String rawTissue = row.values().get("tissue_id");
            TissueNumber tissue = null;
            try {
                tissue = TissueNumber.parse(rawTissue);
            } catch (AnalysisRejectedException e) {
                errors.add(rawTissue == null ? "The tissue ID is missing." : e.getMessage());
            }
            if (tissue != null) {
                Integer earlier = firstRowOf.putIfAbsent(tissue.value(), row.number());
                if (earlier != null) {
                    errors.add("Tissue ID " + tissue.value() + " is already in row " + earlier + ".");
                }
            }
            tissues.add(tissue);
            rowErrors.add(errors);
        }
        Map<TissueNumber, DonorCase> existingCases = donorCases.findAll(tissues.stream().filter(Objects::nonNull).toList());

        for (int i = 0; i < rows.size(); i++) {
            CaseImportFile.Row row = rows.get(i);
            TissueNumber tissue = tissues.get(i);
            List<String> errors = rowErrors.get(i);
            String shown = tissue == null ? row.values().get("tissue_id") : tissue.value();
            Optional<DonorCase> existing = tissue == null ? Optional.empty() : Optional.ofNullable(existingCases.get(tissue));
            CaseDetails base = existing.map(caseService::detailsOf).orElse(null);
            if (errors.isEmpty()) {
                errors.addAll(validate(merge(base, row.values(), errors)));
            }

            String action;
            if (!errors.isEmpty()) {
                action = "error";
            } else if (existing.isEmpty()) {
                action = "create";
            } else {
                action = mode == Mode.UPDATE ? "update" : "skip";
            }
            results.add(new ImportRow(row.number(), shown, action, errors));
            if (errors.isEmpty() && !"skip".equals(action)) {
                valid.add(new Planned(row, tissue, existing, row.values()));
            }
        }

        long withErrors = results.stream().filter(r -> "error".equals(r.action())).count();
        boolean applied = apply && withErrors == 0;
        if (applied) {
            write(valid, results, userId);
        }
        results.sort(Comparator.comparingInt(ImportRow::row));
        return new ImportReport(applied, mode.name().toLowerCase(Locale.ROOT), results.size(),
                count(results, "create"), count(results, "update"), count(results, "skip"), (int) withErrors,
                parsed.ignoredColumns(), results);
    }

    /**
     * Writes the planned rows in one flush with batched statements: all cases, then all audit events, so
     * statements of one kind stay together. A tissue ID that another request created after the check
     * fails the flush; the whole import then rolls back and is reported as a conflict.
     */
    private void write(List<Planned> valid, List<ImportRow> results, Long userId) {
        entityManager.unwrap(Session.class).setJdbcBatchSize(JDBC_BATCH_SIZE);
        List<DonorCase> written = new ArrayList<>();
        for (Planned p : valid) {
            DonorCase donorCase = p.existing().orElseGet(() -> donorCases.newCase(p.tissue(), userId));
            caseService.setDetails(donorCase, merge(p.existing().map(caseService::detailsOf).orElse(null),
                    p.values(), new ArrayList<>()));
            if (p.existing().isEmpty()) {
                donorCases.persist(donorCase);
            }
            written.add(donorCase);
        }
        for (int i = 0; i < valid.size(); i++) {
            audit.recordInTransaction(userId, AuditService.CASE_UPDATE, "case", written.get(i).getId(),
                    valid.get(i).existing().isPresent() ? "bulk import: updated" : "bulk import: created");
        }
        audit.recordInTransaction(userId, AuditService.CASES_IMPORT, null, null,
                count(results, "create") + " created, " + count(results, "update") + " updated, "
                        + count(results, "skip") + " skipped");
        try {
            donorCases.flush();
        } catch (DataIntegrityViolationException e) {
            throw new AnalysisRejectedException(HttpStatus.CONFLICT, "IMPORT_CONFLICT", "file",
                    "Some of these tissue IDs were added by another import or user while this file was being "
                            + "imported, so nothing was imported. Choose the file again: rows that now exist will "
                            + "show as skipped.");
        }
    }

    private static int count(List<ImportRow> rows, String action) {
        return (int) rows.stream().filter(r -> action.equals(r.action())).count();
    }

    // ---------------------------------------------------------------- values

    /**
     * The row's non-blank values over the case's current details (or nothing, for a new case). Values that
     * cannot be read are reported in {@code errors} and left as they were, so the rest is still validated.
     */
    private static CaseDetails merge(CaseDetails base, Map<String, String> values, List<String> errors) {
        Map<String, Object> slitLamp = new LinkedHashMap<>();
        if (base != null && base.slitLamp() != null) {
            slitLamp.putAll(base.slitLamp());
        }
        for (String name : SlitLampFindings.BINARY) {
            String raw = values.get(name);
            if (raw != null) {
                slitLamp.put(name, binary(raw, name, errors));
            }
        }
        SlitLampFindings.CATEGORIES.forEach((name, allowed) -> {
            String raw = values.get(name);
            if (raw != null) {
                // Match the allowed spelling regardless of case ("very mild" -> "Very mild").
                slitLamp.put(name, allowed.stream().filter(a -> a.equalsIgnoreCase(raw)).findFirst().orElse(raw));
            }
        });
        CaseDetails merged = new CaseDetails(
                integer(values, "donor_age_years", base == null ? null : base.donorAgeYears(), errors),
                decimal(values, "death_to_preservation_hours", base == null ? null : base.deathToPreservationHours(), errors),
                date(values, "preservation_date", base == null ? null : base.preservationDate(), errors),
                decimal(values, "ECD_CD_cells_per_mm2", base == null ? null : base.ecd(), errors),
                decimal(values, "CV", base == null ? null : base.cv(), errors),
                decimal(values, "HEX_percent", base == null ? null : base.hexPercent(), errors),
                decimal(values, "SD", base == null ? null : base.sd(), errors),
                integer(values, "Total_Cell_Count", base == null ? null : base.totalCellCount(), errors),
                decimal(values, "Total_Area_um2", base == null ? null : base.totalAreaUm2(), errors),
                slitLamp);
        return merged;
    }

    /** Bean validation (as on the Details form) and the slit-lamp rules; returns the messages. */
    private List<String> validate(CaseDetails details) {
        List<String> errors = new ArrayList<>();
        Set<ConstraintViolation<CaseDetails>> violations = validator.validate(details);
        violations.stream()
                .sorted(Comparator.comparing(v -> v.getPropertyPath().toString()))
                .forEach(v -> errors.add(label(v.getPropertyPath().toString()) + " " + v.getMessage() + "."));
        try {
            SlitLampFindings.normalise(details.slitLamp());
        } catch (AnalysisRejectedException e) {
            errors.add(e.getMessage());
        }
        return errors;
    }

    private static String label(String property) {
        return switch (property) {
            case "donorAgeYears" -> "donor_age_years";
            case "deathToPreservationHours" -> "death_to_preservation_hours";
            case "ecd" -> "ECD_CD_cells_per_mm2";
            case "cv" -> "CV";
            case "hexPercent" -> "HEX_percent";
            case "sd" -> "SD";
            case "totalCellCount" -> "Total_Cell_Count";
            case "totalAreaUm2" -> "Total_Area_um2";
            default -> property;
        };
    }

    private static Double decimal(Map<String, String> values, String column, Double current, List<String> errors) {
        String raw = values.get(column);
        if (raw == null) {
            return current;
        }
        try {
            double value = Double.parseDouble(raw.replace(",", ""));
            if (!Double.isFinite(value)) {
                throw new NumberFormatException();
            }
            return value;
        } catch (NumberFormatException e) {
            errors.add(column + " must be a number (got \"" + raw + "\").");
            return current;
        }
    }

    private static Integer integer(Map<String, String> values, String column, Integer current, List<String> errors) {
        Double value = decimal(values, column, current == null ? null : current.doubleValue(), errors);
        if (value == null) {
            return null;
        }
        if (value != Math.rint(value)) {
            errors.add(column + " must be a whole number (got \"" + values.get(column) + "\").");
            return current;
        }
        return value.intValue();
    }

    private static LocalDate date(Map<String, String> values, String column, LocalDate current, List<String> errors) {
        String raw = values.get(column);
        if (raw == null) {
            return current;
        }
        try {
            return LocalDate.parse(raw.length() > 10 ? raw.substring(0, 10) : raw);
        } catch (DateTimeParseException e) {
            errors.add(column + " must be a date as YYYY-MM-DD (got \"" + raw + "\").");
            return current;
        }
    }

    private static Integer binary(String raw, String column, List<String> errors) {
        return switch (raw.toLowerCase(Locale.ROOT)) {
            case "1", "1.0", "yes", "y", "true" -> 1;
            case "0", "0.0", "no", "n", "false" -> 0;
            default -> {
                errors.add(column + " must be 1/0 or Yes/No (got \"" + raw + "\").");
                yield null;
            }
        };
    }

}
