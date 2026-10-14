package com.cornealai.backend.user;

import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import com.cornealai.backend.user.repository.AppUserRepository;
import com.cornealai.backend.user.service.AdminBootstrapRunner;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "app.bootstrap.admin.email=Bootstrap.Admin@CornealAI.test",
        "app.bootstrap.admin.username=bootstrap.admin",
        "app.bootstrap.admin.password=Bootstrap-Password-123"
})
class AdminBootstrapIntegrationTests {

    @Autowired
    private AppUserRepository userRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private AdminBootstrapRunner runner;

    @Test
    void createsInitialAdministratorOnceWithHashedPassword() {
        AppUser admin = userRepository.findByUsernameOrEmail("bootstrap.admin@cornealai.test").orElseThrow();

        assertThat(admin.getRole().getName()).isEqualTo(RoleName.ADMIN);
        assertThat(admin.getPasswordHash()).isNotEqualTo("Bootstrap-Password-123");
        assertThat(passwordEncoder.matches("Bootstrap-Password-123", admin.getPasswordHash())).isTrue();

        long before = userRepository.count();
        runner.run(null); // an ADMIN now exists, so this must be a no-op
        assertThat(userRepository.count()).isEqualTo(before);
    }
}
