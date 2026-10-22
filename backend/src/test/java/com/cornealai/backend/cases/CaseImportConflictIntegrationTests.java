package com.cornealai.backend.cases;

import com.cornealai.backend.cases.service.DonorCaseService;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * A tissue ID created by another request between the import's lookup and its write (e.g. a retried
 * import still running) must give a clear conflict, not a server error.
 */
class CaseImportConflictIntegrationTests extends IntegrationTestSupport {

    @MockitoSpyBean
    private DonorCaseService donorCases;

    @Test
    void caseCreatedAfterTheLookupIsReportedAsAConflict() throws Exception {
        AppUser nurse = createUser("nurse.conflict", RoleName.NURSE);
        donorCases.findOrCreate(TissueNumber.parse("12656R"), nurse.getId());
        // The lookup does not see it yet, as when another import creates it meanwhile.
        doReturn(Map.of()).when(donorCases).findAll(any());

        mockMvc.perform(multipart("/api/cases/import")
                        .file(new MockMultipartFile("file", "cases.csv", MediaType.TEXT_PLAIN_VALUE,
                                "tissue_id,ECD\n12656R,2400\n12657L,2500\n".getBytes(StandardCharsets.UTF_8)))
                        .param("mode", "create")
                        .param("apply", "true")
                        .header(HttpHeaders.AUTHORIZATION, bearer(nurse)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("IMPORT_CONFLICT"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("nothing was imported")));
    }
}
