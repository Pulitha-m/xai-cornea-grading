package com.cornealai.backend.cases;

import com.cornealai.backend.cases.repository.DonorCaseRepository;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.ResultActions;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Bulk case import from CSV and Excel: check first, then import all rows or none. */
class CaseImportIntegrationTests extends IntegrationTestSupport {

    @Autowired
    private DonorCaseRepository cases;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private jakarta.persistence.EntityManager entityManager;

    private AppUser nurse;

    @BeforeEach
    void setUp() {
        nurse = createUser("nurse.import", RoleName.NURSE);
    }

    @Test
    void templateListsEveryColumn() throws Exception {
        String csv = mockMvc.perform(get("/api/cases/import/template").header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition", containsString("case-import-template.csv")))
                .andReturn().getResponse().getContentAsString();
        String[] header = csv.lines().findFirst().orElseThrow().split(",");
        assertThat(header).hasSize(28).startsWith("tissue_id").contains("ECD_CD_cells_per_mm2", "Stroma_Has_Scar",
                "Epi_Exposure_Severity");
    }

    @Test
    void checkReportsEveryRowAndChangesNothing() throws Exception {
        String csv = """
                Tissue ID,Age,ECD,HEX,Stroma_Has_Scar,Descemet_Fold_Severity,Comments
                 12656r ,54,2400,58,Yes,very mild,first
                CASE-1,60,2500,50,0,,bad id
                12656R,61,2600,55,0,,duplicate
                12657L,abc,2700,120,maybe,Severe,bad values
                12658R,,2300,,,,minimal
                """;

        upload(csv, "cases.csv", "create", false)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.applied").value(false))
                .andExpect(jsonPath("$.rows").value(5))
                .andExpect(jsonPath("$.created").value(2))
                .andExpect(jsonPath("$.withErrors").value(3))
                .andExpect(jsonPath("$.ignoredColumns[0]").value("Comments"))
                .andExpect(jsonPath("$.details[0].row").value(2))
                .andExpect(jsonPath("$.details[0].tissueId").value("12656R"))
                .andExpect(jsonPath("$.details[0].action").value("create"))
                .andExpect(jsonPath("$.details[1].errors[0]").value(containsString("five digits")))
                .andExpect(jsonPath("$.details[2].errors[0]").value("Tissue ID 12656R is already in row 2."))
                .andExpect(jsonPath("$.details[3].errors", hasSize(4)))
                .andExpect(jsonPath("$.details[3].errors", hasItem(containsString("donor_age_years must be a number"))))
                .andExpect(jsonPath("$.details[4].action").value("create"));
        assertThat(cases.count()).isZero();
    }

    @Test
    void importIsRefusedWhileAnyRowHasAnError() throws Exception {
        upload("tissue_id,ECD_CD_cells_per_mm2\n12656R,2400\n12657L,-5\n", "cases.csv", "create", true)
                .andExpect(status().isUnprocessableContent())
                .andExpect(jsonPath("$.applied").value(false))
                .andExpect(jsonPath("$.details[1].errors[0]").value(containsString("ECD_CD_cells_per_mm2")));
        assertThat(cases.count()).isZero();
    }

    @Test
    void validFileIsImportedEncryptedAndAudited() throws Exception {
        upload("tissue_id,donor_age_years,ECD_CD_cells_per_mm2,CV,preservation_date,Stroma_Is_Clear\n"
                + "12656R,54,2400,32,2026-10-15,1\n12657L,,2500,,,\n", "cases.csv", "create", true)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.applied").value(true))
                .andExpect(jsonPath("$.created").value(2));

        mockMvc.perform(get("/api/cases").param("tissueId", "12656R").header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(jsonPath("$[0].details.donorAgeYears").value(54))
                .andExpect(jsonPath("$[0].details.ecd").value(2400.0))
                .andExpect(jsonPath("$[0].details.preservationDate").value("2026-10-15"))
                .andExpect(jsonPath("$[0].details.slitLamp.Stroma_Is_Clear").value(1));
        entityManager.flush();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM audit_events WHERE action = 'CASES_IMPORT'", Integer.class))
                .isEqualTo(1);
        for (byte[] stored : jdbc.queryForList("SELECT tissue_number_enc FROM donor_cases", byte[].class)) {
            assertThat(new String(stored, StandardCharsets.ISO_8859_1)).doesNotContain("1265");
        }
    }

    @Test
    void createModeSkipsExistingCasesAndUpdateModeKeepsValuesForBlankCells() throws Exception {
        upload("tissue_id,ECD_CD_cells_per_mm2,CV\n12656R,2400,32\n", "cases.csv", "create", true)
                .andExpect(status().isOk());

        upload("tissue_id,ECD_CD_cells_per_mm2,CV\n12656R,2500,\n12657L,2600,30\n", "cases.csv", "create", true)
                .andExpect(jsonPath("$.created").value(1))
                .andExpect(jsonPath("$.skipped").value(1));
        mockMvc.perform(get("/api/cases").param("tissueId", "12656R").header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(jsonPath("$[0].details.ecd").value(2400.0));

        upload("tissue_id,ECD_CD_cells_per_mm2,CV\n12656R,2500,\n", "cases.csv", "update", true)
                .andExpect(jsonPath("$.updated").value(1));
        mockMvc.perform(get("/api/cases").param("tissueId", "12656R").header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(jsonPath("$[0].details.ecd").value(2500.0))
                .andExpect(jsonPath("$[0].details.cv").value(32.0));
    }

    @Test
    void excelWorkbooksAreReadWithNumbersAndDates() throws Exception {
        byte[] xlsx;
        try (XSSFWorkbook workbook = new XSSFWorkbook(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("Cases");
            Row header = sheet.createRow(0);
            String[] columns = {"Tissue ID", "Donor age", "ECD", "Preservation date", "Total_Cell_Count"};
            for (int i = 0; i < columns.length; i++) {
                header.createCell(i).setCellValue(columns[i]);
            }
            CellStyle dateStyle = workbook.createCellStyle();
            dateStyle.setDataFormat(workbook.getCreationHelper().createDataFormat().getFormat("dd/mm/yyyy"));
            Row row = sheet.createRow(1);
            row.createCell(0).setCellValue("12656R");
            row.createCell(1).setCellValue(54);
            row.createCell(2).setCellValue(2400.5);
            row.createCell(3).setCellValue(LocalDate.of(2026, 10, 15));
            row.getCell(3).setCellStyle(dateStyle);
            row.createCell(4).setCellValue(120);
            workbook.write(out);
            xlsx = out.toByteArray();
        }

        mockMvc.perform(multipart("/api/cases/import")
                        .file(new MockMultipartFile("file", "cases.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", xlsx))
                        .param("apply", "true")
                        .header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.created").value(1));
        mockMvc.perform(get("/api/cases").param("tissueId", "12656R").header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(jsonPath("$[0].details.donorAgeYears").value(54))
                .andExpect(jsonPath("$[0].details.ecd").value(2400.5))
                .andExpect(jsonPath("$[0].details.preservationDate").value("2026-10-15"))
                .andExpect(jsonPath("$[0].details.totalCellCount").value(120));
    }

    @Test
    void semicolonSeparatedCsvWithByteOrderMarkIsRead() throws Exception {
        upload("﻿tissue_id;ECD_CD_cells_per_mm2\r\n12656R;2400\r\n", "cases.csv", "create", false)
                .andExpect(jsonPath("$.created").value(1))
                .andExpect(jsonPath("$.withErrors").value(0));
    }

    @Test
    void unreadableFilesAreRejected() throws Exception {
        upload("ECD,CV\n2400,32\n", "cases.csv", "create", false)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_IMPORT_FILE"))
                .andExpect(jsonPath("$.message").value(containsString("tissue_id")));
        upload("tissue_id,ECD,ecd\n12656R,1,2\n", "cases.csv", "create", false)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(containsString("appears twice")));
        upload("anything", "cases.xls", "create", false)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(containsString(".xlsx")));
        upload("PK not really a workbook", "cases.xlsx", "create", false)
                .andExpect(status().isBadRequest());
        upload("tissue_id\n12656R\n", "cases.csv", "replace", false).andExpect(status().isBadRequest());
    }

    @Test
    void onlyClinicalRolesImport() throws Exception {
        AppUser manager = createUser("manager.import", RoleName.MANAGER);
        mockMvc.perform(multipart("/api/cases/import")
                        .file(new MockMultipartFile("file", "cases.csv", "text/csv", "tissue_id\n12656R\n".getBytes()))
                        .header(HttpHeaders.AUTHORIZATION, bearer(manager)))
                .andExpect(status().isForbidden());
    }

    private ResultActions upload(String content, String filename, String mode, boolean apply) throws Exception {
        return mockMvc.perform(multipart("/api/cases/import")
                .file(new MockMultipartFile("file", filename, MediaType.TEXT_PLAIN_VALUE,
                        content.getBytes(StandardCharsets.UTF_8)))
                .param("mode", mode)
                .param("apply", String.valueOf(apply))
                .header(HttpHeaders.AUTHORIZATION, bearer(nurse)));
    }
}
