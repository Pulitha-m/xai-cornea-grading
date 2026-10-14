package com.cornealai.backend.auth;

import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.RoleName;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Exercises the real cookie-to-header CSRF flow used by the frontend.
 * <p>
 * Runs in its own application context: spring-security-test's {@code csrf()}
 * post-processor (used elsewhere) permanently swaps the CSRF repository of the
 * shared MockMvc, which would hide the real cookie repository.
 */
@TestPropertySource(properties = "test.context=csrf-flow")
class CsrfFlowIntegrationTests extends IntegrationTestSupport {

    @Test
    void xsrfCookieMustBeEchoedInHeaderForLogin() throws Exception {
        createUserWithPassword("dr.xsrf", RoleName.DOCTOR);

        MvcResult csrf = mockMvc.perform(get("/api/auth/csrf"))
                .andExpect(status().isNoContent())
                .andReturn();

        Cookie xsrf = csrf.getResponse().getCookie("XSRF-TOKEN");
        assertThat(xsrf).isNotNull();
        assertThat(xsrf.isHttpOnly()).as("frontend must be able to read it").isFalse();

        String body = """
                {"identifier":"dr.xsrf","password":"%s"}
                """.formatted(PASSWORD);

        // Cookie without matching header -> rejected
        mockMvc.perform(post("/api/auth/login")
                        .cookie(new Cookie("XSRF-TOKEN", xsrf.getValue()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isForbidden());

        // Header that does not match the cookie -> rejected
        mockMvc.perform(post("/api/auth/login")
                        .cookie(new Cookie("XSRF-TOKEN", xsrf.getValue()))
                        .header("X-XSRF-TOKEN", "forged-value")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isForbidden());

        // Cookie echoed in header -> accepted
        mockMvc.perform(post("/api/auth/login")
                        .cookie(new Cookie("XSRF-TOKEN", xsrf.getValue()))
                        .header("X-XSRF-TOKEN", xsrf.getValue())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());
    }
}
