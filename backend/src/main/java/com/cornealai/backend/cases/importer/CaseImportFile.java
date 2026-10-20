package com.cornealai.backend.cases.importer;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.cases.SlitLampFindings;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.DateUtil;
import org.apache.poi.ss.usermodel.FormulaEvaluator;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.http.HttpStatus;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Reads a case import file (CSV, or the first sheet of an .xlsx workbook) into rows keyed by canonical
 * column names. Headers are matched ignoring case, spaces and punctuation, so "Tissue ID", "tissue_id"
 * and "TISSUEID" are the same column; a few short aliases are accepted (e.g. "ECD", "HEX", "Age").
 */
public final class CaseImportFile {

    public static final long MAX_BYTES = 5L * 1024 * 1024;
    public static final int MAX_ROWS = 2000;

    /** Canonical column names, in template order. */
    public static final List<String> COLUMNS = columns();

    private static final Map<String, String> ALIASES = aliases();

    /** One data row: its number as the user sees it (header = row 1) and its non-blank values. */
    public record Row(int number, Map<String, String> values) {
    }

    public record Parsed(List<Row> rows, List<String> ignoredColumns) {
    }

    private CaseImportFile() {
    }

    public static Parsed read(String filename, byte[] data) {
        if (data == null || data.length == 0) {
            throw invalid("The file is empty.");
        }
        if (data.length > MAX_BYTES) {
            throw invalid("The file is larger than 5 MB. Split it into smaller files.");
        }
        String name = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
        boolean zip = data.length > 2 && data[0] == 'P' && data[1] == 'K';
        if (name.endsWith(".xlsx") || zip) {
            return readXlsx(data);
        }
        if (name.endsWith(".xls")) {
            throw invalid("Old .xls workbooks are not supported. Save the file as .xlsx or CSV.");
        }
        return readCsv(new String(data, StandardCharsets.UTF_8));
    }

    /** The template's header line. */
    public static String templateCsv() {
        return String.join(",", COLUMNS) + "\r\n"
                + "12656R,54,6,2026-10-15,2400,32,58,110,120,50000,1,1,0,0,0,0,0,0,0,0,0,0,0,,,,,\r\n";
    }

    // ---------------------------------------------------------------- CSV

    private static Parsed readCsv(String text) {
        if (text.startsWith("﻿")) {
            text = text.substring(1);  // Excel's UTF-8 byte order mark
        }
        String firstLine = text.lines().findFirst().orElse("");
        char delimiter = firstLine.contains(";") && !firstLine.contains(",") ? ';' : ',';
        CSVFormat format = CSVFormat.DEFAULT.builder().setDelimiter(delimiter).setIgnoreEmptyLines(true)
                .setTrim(true).get();
        try (CSVParser parser = CSVParser.parse(new StringReader(text), format)) {
            List<CSVRecord> records = parser.getRecords();
            if (records.isEmpty()) {
                throw invalid("The file has no header row.");
            }
            List<String> header = new ArrayList<>();
            records.getFirst().forEach(header::add);
            Header mapped = map(header);
            List<Row> rows = new ArrayList<>();
            for (int i = 1; i < records.size(); i++) {
                CSVRecord record = records.get(i);
                Map<String, String> values = new LinkedHashMap<>();
                for (int c = 0; c < Math.min(record.size(), mapped.columns().size()); c++) {
                    put(values, mapped.columns().get(c), record.get(c));
                }
                add(rows, (int) record.getRecordNumber(), values);
            }
            return new Parsed(rows, mapped.ignored());
        } catch (IOException | IllegalStateException | java.io.UncheckedIOException e) {
            throw invalid("The CSV file could not be read. Check that it is saved as CSV (comma separated).");
        }
    }

    // ---------------------------------------------------------------- Excel

    private static Parsed readXlsx(byte[] data) {
        try (Workbook workbook = new XSSFWorkbook(new ByteArrayInputStream(data))) {
            if (workbook.getNumberOfSheets() == 0) {
                throw invalid("The workbook has no sheets.");
            }
            Sheet sheet = workbook.getSheetAt(0);
            FormulaEvaluator evaluator = workbook.getCreationHelper().createFormulaEvaluator();
            DataFormatter formatter = new DataFormatter(Locale.ROOT);
            org.apache.poi.ss.usermodel.Row headerRow = sheet.getRow(sheet.getFirstRowNum());
            if (headerRow == null) {
                throw invalid("The first sheet has no header row.");
            }
            List<String> header = new ArrayList<>();
            for (int c = 0; c < headerRow.getLastCellNum(); c++) {
                header.add(text(headerRow.getCell(c), formatter, evaluator));
            }
            Header mapped = map(header);
            List<Row> rows = new ArrayList<>();
            for (int r = sheet.getFirstRowNum() + 1; r <= sheet.getLastRowNum(); r++) {
                org.apache.poi.ss.usermodel.Row row = sheet.getRow(r);
                if (row == null) {
                    continue;
                }
                Map<String, String> values = new LinkedHashMap<>();
                for (int c = 0; c < mapped.columns().size(); c++) {
                    put(values, mapped.columns().get(c), text(row.getCell(c), formatter, evaluator));
                }
                add(rows, r + 1, values);
            }
            return new Parsed(rows, mapped.ignored());
        } catch (AnalysisRejectedException e) {
            throw e;
        } catch (IOException | RuntimeException e) {
            throw invalid("The Excel file could not be read. Save it as .xlsx or CSV and try again.");
        }
    }

    private static String text(Cell cell, DataFormatter formatter, FormulaEvaluator evaluator) {
        if (cell == null) {
            return "";
        }
        CellType type = cell.getCellType() == CellType.FORMULA ? evaluator.evaluateFormulaCell(cell) : cell.getCellType();
        if (type == CellType.NUMERIC && DateUtil.isCellDateFormatted(cell)) {
            return cell.getLocalDateTimeCellValue().toLocalDate().toString();
        }
        if (type == CellType.NUMERIC) {
            double value = cell.getNumericCellValue();
            return value == Math.rint(value) && Math.abs(value) < 1e15 ? Long.toString((long) value) : Double.toString(value);
        }
        return formatter.formatCellValue(cell, evaluator).trim();
    }

    // ---------------------------------------------------------------- headers and rows

    private record Header(List<String> columns, List<String> ignored) {
    }

    /** Canonical name per position (null = ignored column). Requires the tissue ID column, rejects duplicates. */
    private static Header map(List<String> header) {
        List<String> columns = new ArrayList<>();
        List<String> ignored = new ArrayList<>();
        for (String raw : header) {
            String name = raw == null ? "" : raw.strip();
            String canonical = ALIASES.get(normalise(name));
            if (canonical != null && columns.contains(canonical)) {
                throw invalid("The column \"" + name + "\" appears twice.");
            }
            columns.add(canonical);
            if (canonical == null && !name.isEmpty()) {
                ignored.add(name);
            }
        }
        if (!columns.contains("tissue_id")) {
            throw invalid("The file needs a \"tissue_id\" column. Download the template to see the columns.");
        }
        return new Header(columns, ignored);
    }

    private static void put(Map<String, String> values, String column, String value) {
        if (column != null && value != null && !value.isBlank()) {
            values.put(column, value.strip());
        }
    }

    private static void add(List<Row> rows, int number, Map<String, String> values) {
        if (values.isEmpty()) {
            return;  // blank line
        }
        if (rows.size() >= MAX_ROWS) {
            throw invalid("The file has more than " + MAX_ROWS + " rows. Split it into smaller files.");
        }
        rows.add(new Row(number, values));
    }

    static String normalise(String header) {
        return header.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]", "");
    }

    private static List<String> columns() {
        List<String> columns = new ArrayList<>(List.of("tissue_id", "donor_age_years", "death_to_preservation_hours",
                "preservation_date", "ECD_CD_cells_per_mm2", "CV", "HEX_percent", "SD", "Total_Cell_Count",
                "Total_Area_um2"));
        columns.addAll(SlitLampFindings.BINARY);
        columns.addAll(SlitLampFindings.CATEGORIES.keySet());
        return List.copyOf(columns);
    }

    private static Map<String, String> aliases() {
        Map<String, String> map = new LinkedHashMap<>();
        COLUMNS.forEach(c -> map.put(normalise(c), c));
        map.put("donorage", "donor_age_years");
        map.put("age", "donor_age_years");
        map.put("deathtopreservationh", "death_to_preservation_hours");
        map.put("deathtopreservation", "death_to_preservation_hours");
        map.put("ecd", "ECD_CD_cells_per_mm2");
        map.put("hex", "HEX_percent");
        map.put("cellcount", "Total_Cell_Count");
        map.put("totalarea", "Total_Area_um2");
        return Map.copyOf(map);
    }

    private static AnalysisRejectedException invalid(String message) {
        return new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_IMPORT_FILE", "file", message);
    }
}
