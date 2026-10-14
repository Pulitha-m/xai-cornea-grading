package com.cornealai.backend.auth;

import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.test.web.servlet.MvcResult;

import javax.crypto.spec.SecretKeySpec;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class AuthIntegrationTests extends IntegrationTestSupport {

    private static final String REFRESH_COOKIE = "cornealai_refresh";
    private static final String GENERIC_LOGIN_ERROR = "Invalid username/email or password.";

    @Autowired
    private JwtEncoder jwtEncoder;

    // ---------- Login ----------

    @Test
    void loginWithUsernameReturnsAccessTokenAndHttpOnlyRefreshCookie() throws Exception {
        createUserWithPassword("dr.silva", RoleName.DOCTOR);

        MvcResult result = mockMvc.perform(login("dr.silva", PASSWORD, false))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").isNotEmpty())
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.user.username").value("dr.silva"))
                .andExpect(jsonPath("$.user.role").value("DOCTOR"))
                .andExpect(jsonPath("$.user.permissions[0]").value("analysis:run"))
                .andReturn();

        String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);
        assertThat(setCookie)
                .startsWith(REFRESH_COOKIE + "=")
                .contains("HttpOnly", "Secure", "SameSite=Strict", "Path=/api/auth")
                .doesNotContain("Max-Age"); // no "remember me" -> browser-session cookie
    }

    @Test
    void loginWithEmailAndRememberMeSetsPersistentCookie() throws Exception {
        createUserWithPassword("nurse.perera", RoleName.NURSE);

        MvcResult result = mockMvc.perform(login("Nurse.Perera@CornealAI.test", PASSWORD, true))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.role").value("NURSE"))
                .andReturn();

        assertThat(result.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=");
    }

    @Test
    void wrongPasswordAndUnknownUserGetTheSameGenericError() throws Exception {
        createUserWithPassword("dr.fernando", RoleName.DOCTOR);

        mockMvc.perform(login("dr.fernando", "wrong-password-123", false))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value(GENERIC_LOGIN_ERROR))
                .andExpect(header().doesNotExist(HttpHeaders.SET_COOKIE));

        mockMvc.perform(login("nobody", "wrong-password-123", false))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value(GENERIC_LOGIN_ERROR));
    }

    @Test
    void accountIsLockedAfterRepeatedFailures() throws Exception {
        createUserWithPassword("dr.locked", RoleName.DOCTOR);

        for (int i = 0; i < 5; i++) {
            mockMvc.perform(login("dr.locked", "wrong-password-123", false))
                    .andExpect(status().isUnauthorized());
        }

        // Even the correct password is now rejected, with the same generic message.
        mockMvc.perform(login("dr.locked", PASSWORD, false))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value(GENERIC_LOGIN_ERROR));
    }

    @Test
    void disabledAccountCannotLogIn() throws Exception {
        AppUser user = createUserWithPassword("dr.disabled", RoleName.DOCTOR);
        user.setEnabled(false);
        userRepository.saveAndFlush(user);

        mockMvc.perform(login("dr.disabled", PASSWORD, false))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value(GENERIC_LOGIN_ERROR));
    }

    @Test
    void roleSuppliedByClientDuringLoginIsIgnored() throws Exception {
        createUserWithPassword("nurse.sneaky", RoleName.NURSE);

        mockMvc.perform(post("/api/auth/login").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"identifier":"nurse.sneaky","password":"%s","role":"ADMIN","permissions":["users:manage"]}
                                """.formatted(PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.role").value("NURSE"));
    }

    @Test
    void loginRequiresCsrfToken() throws Exception {
        createUserWithPassword("dr.csrf", RoleName.DOCTOR);

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginJson("dr.csrf", PASSWORD, false)))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginValidatesRequestBody() throws Exception {
        mockMvc.perform(post("/api/auth/login").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"identifier\":\"\",\"password\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.identifier").exists())
                .andExpect(jsonPath("$.fieldErrors.password").exists());
    }

    // ---------- Access tokens ----------

    @Test
    void missingTokenOnProtectedEndpointReturns401() throws Exception {
        mockMvc.perform(get("/api/auth/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void validTokenAccessesProtectedEndpoint() throws Exception {
        AppUser doctor = createUser("dr.valid", RoleName.DOCTOR);

        mockMvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, bearer(doctor)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(doctor.getId()))
                .andExpect(jsonPath("$.role").value("DOCTOR"))
                .andExpect(jsonPath("$.passwordHash").doesNotExist());
    }

    @Test
    void expiredTokenReturns401() throws Exception {
        AppUser doctor = createUser("dr.expired", RoleName.DOCTOR);
        Instant past = Instant.now().minusSeconds(3600);

        String expired = sign(jwtEncoder, JwtClaimsSet.builder()
                .issuer("corneal-ai")
                .audience(List.of("corneal-ai-web"))
                .subject(String.valueOf(doctor.getId()))
                .issuedAt(past)
                .expiresAt(past.plusSeconds(900))
                .build());

        mockMvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, "Bearer " + expired))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(HttpHeaders.WWW_AUTHENTICATE, "Bearer error=\"invalid_token\""));
    }

    @Test
    void malformedTokenReturns401() throws Exception {
        mockMvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, "Bearer not.a.jwt"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void tokenSignedWithAnotherKeyReturns401() throws Exception {
        AppUser admin = createUser("admin.forged", RoleName.ADMIN);
        JwtEncoder attackerEncoder = NimbusJwtEncoder.withSecretKey(
                new SecretKeySpec("attacker-controlled-secret-key-32-bytes!!".getBytes(), "HmacSHA256")).build();

        String forged = sign(attackerEncoder, validClaims(admin.getId(), "ADMIN"));

        mockMvc.perform(get("/api/users").header(HttpHeaders.AUTHORIZATION, "Bearer " + forged))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void roleClaimInTokenIsNotTrusted() throws Exception {
        // Correctly signed token for a nurse that claims ADMIN: authorities come from the database.
        AppUser nurse = createUser("nurse.claims", RoleName.NURSE);
        String token = sign(jwtEncoder, validClaims(nurse.getId(), "ADMIN"));

        mockMvc.perform(get("/api/users").header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isForbidden());
    }

    @Test
    void tokenOfDisabledUserIsRejected() throws Exception {
        AppUser doctor = createUser("dr.revoked", RoleName.DOCTOR);
        String token = bearer(doctor);

        doctor.setEnabled(false);
        userRepository.saveAndFlush(doctor);

        mockMvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isUnauthorized());
    }

    // ---------- Refresh & logout ----------

    @Test
    void refreshRotatesTokenAndDetectsReuse() throws Exception {
        createUserWithPassword("dr.refresh", RoleName.DOCTOR);
        Cookie original = refreshCookie(mockMvc.perform(login("dr.refresh", PASSWORD, false)).andReturn());

        MvcResult refreshed = mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(original))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").isNotEmpty())
                .andExpect(jsonPath("$.user.username").value("dr.refresh"))
                .andReturn();
        Cookie rotated = refreshCookie(refreshed);
        assertThat(rotated.getValue()).isNotEqualTo(original.getValue());

        // Replaying the old token is treated as theft: rejected and the cookie is cleared...
        MvcResult reused = mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(original))
                .andExpect(status().isUnauthorized())
                .andReturn();
        assertThat(reused.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");

        // ...and the whole session is revoked, including the newest token.
        mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(rotated))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void refreshWithoutCookieReturns401() throws Exception {
        mockMvc.perform(post("/api/auth/refresh").with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void refreshRequiresCsrfToken() throws Exception {
        createUserWithPassword("dr.refreshcsrf", RoleName.DOCTOR);
        Cookie cookie = refreshCookie(mockMvc.perform(login("dr.refreshcsrf", PASSWORD, false)).andReturn());

        mockMvc.perform(post("/api/auth/refresh").cookie(cookie))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutRevokesRefreshTokenAndClearsCookie() throws Exception {
        createUserWithPassword("dr.logout", RoleName.DOCTOR);
        Cookie cookie = refreshCookie(mockMvc.perform(login("dr.logout", PASSWORD, false)).andReturn());

        MvcResult logout = mockMvc.perform(post("/api/auth/logout").with(csrf()).cookie(cookie))
                .andExpect(status().isNoContent())
                .andReturn();
        assertThat(logout.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");

        mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(cookie))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void roleChangeRevokesExistingRefreshTokens() throws Exception {
        AppUser admin = createUser("admin.rolechange", RoleName.ADMIN);
        AppUser nurse = createUserWithPassword("nurse.rolechange", RoleName.NURSE);
        Cookie cookie = refreshCookie(mockMvc.perform(login("nurse.rolechange", PASSWORD, false)).andReturn());

        mockMvc.perform(put("/api/users/" + nurse.getId() + "/role")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role\":\"SUPPORT_STAFF\"}"))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/auth/refresh").with(csrf()).cookie(cookie))
                .andExpect(status().isUnauthorized());
    }

    // ---------- Helpers ----------

    private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder put(String url) {
        return org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put(url);
    }

    private static org.springframework.test.web.servlet.RequestBuilder login(String identifier, String password, boolean rememberMe) {
        return post("/api/auth/login").with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(loginJson(identifier, password, rememberMe));
    }

    private static String loginJson(String identifier, String password, boolean rememberMe) {
        return """
                {"identifier":"%s","password":"%s","rememberMe":%s}
                """.formatted(identifier, password, rememberMe);
    }

    private static Cookie refreshCookie(MvcResult result) {
        Cookie cookie = result.getResponse().getCookie(REFRESH_COOKIE);
        assertThat(cookie).as("refresh cookie").isNotNull();
        return new Cookie(REFRESH_COOKIE, cookie.getValue());
    }

    private static JwtClaimsSet validClaims(Long userId, String roleClaim) {
        Instant now = Instant.now();
        return JwtClaimsSet.builder()
                .issuer("corneal-ai")
                .audience(List.of("corneal-ai-web"))
                .subject(String.valueOf(userId))
                .issuedAt(now)
                .expiresAt(now.plusSeconds(600))
                .claim("role", roleClaim)
                .build();
    }

    private static String sign(JwtEncoder encoder, JwtClaimsSet claims) {
        JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).type("JWT").build();
        return encoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
    }
}
