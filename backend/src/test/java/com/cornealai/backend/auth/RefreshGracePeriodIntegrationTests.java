package com.cornealai.backend.auth;

import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.RoleName;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Two tabs refreshing with the same cookie must not log the user out. */
@TestPropertySource(properties = "app.security.refresh-token.reuse-grace-period=1m")
class RefreshGracePeriodIntegrationTests extends IntegrationTestSupport {

    private static final String REFRESH_COOKIE = "cornealai_refresh";

    @Test
    void concurrentRefreshWithinGracePeriodKeepsSessionAlive() throws Exception {
        createUserWithPassword("dr.tabs", RoleName.DOCTOR);

        MvcResult login = mockMvc.perform(post("/api/auth/login").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"identifier\":\"dr.tabs\",\"password\":\"" + PASSWORD + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        Cookie original = new Cookie(REFRESH_COOKIE, login.getResponse().getCookie(REFRESH_COOKIE).getValue());

        // Tab A rotates the token.
        MvcResult tabA = mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(original))
                .andExpect(status().isOk())
                .andReturn();
        Cookie rotated = new Cookie(REFRESH_COOKIE, tabA.getResponse().getCookie(REFRESH_COOKIE).getValue());

        // Tab B presents the old token moments later: rejected, but the cookie is left alone...
        MvcResult tabB = mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(original))
                .andExpect(status().isUnauthorized())
                .andReturn();
        assertThat(tabB.getResponse().getHeader(HttpHeaders.SET_COOKIE)).isNull();

        // ...and the session is still valid with the rotated token.
        mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(rotated))
                .andExpect(status().isOk());
    }
}
