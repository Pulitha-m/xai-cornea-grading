package com.cornealai.backend.support;

import com.cornealai.backend.security.AppUserDetails;
import com.cornealai.backend.security.JwtService;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import com.cornealai.backend.user.repository.AppUserRepository;
import com.cornealai.backend.user.repository.RoleRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

/**
 * Base class for integration tests. Each test runs in a transaction that is rolled back.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
public abstract class IntegrationTestSupport {

    protected static final String PASSWORD = "Correct-Horse-Battery-9";

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected AppUserRepository userRepository;

    @Autowired
    protected RoleRepository roleRepository;

    @Autowired
    protected PasswordEncoder passwordEncoder;

    @Autowired
    protected JwtService jwtService;

    /** Creates a user with a real BCrypt hash of {@link #PASSWORD}, for login tests. */
    protected AppUser createUserWithPassword(String username, RoleName role) {
        return saveUser(username, role, passwordEncoder.encode(PASSWORD));
    }

    /** Creates a user without a usable password; faster when only a token is needed. */
    protected AppUser createUser(String username, RoleName role) {
        return saveUser(username, role, "unused-hash");
    }

    protected String bearer(AppUser user) {
        return "Bearer " + jwtService.issueAccessToken(AppUserDetails.from(user)).value();
    }

    private AppUser saveUser(String username, RoleName role, String passwordHash) {
        AppUser user = new AppUser();
        user.setUsername(username);
        user.setEmail(username + "@cornealai.test");
        user.setFullName("Test " + username);
        user.setRole(roleRepository.findByName(role).orElseThrow());
        user.setPasswordHash(passwordHash);
        user.setEnabled(true);
        return userRepository.saveAndFlush(user);
    }
}
