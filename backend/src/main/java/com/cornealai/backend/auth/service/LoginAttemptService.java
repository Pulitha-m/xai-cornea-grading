package com.cornealai.backend.auth.service;

import com.cornealai.backend.security.SecurityProperties;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.repository.AppUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

/** Tracks failed logins and temporarily locks accounts to slow down password guessing. */
@Service
public class LoginAttemptService {

    private static final Logger log = LoggerFactory.getLogger(LoginAttemptService.class);

    private final AppUserRepository userRepository;
    private final SecurityProperties.Login properties;

    public LoginAttemptService(AppUserRepository userRepository, SecurityProperties securityProperties) {
        this.userRepository = userRepository;
        this.properties = securityProperties.login();
    }

    /** Records a failed password attempt. Unknown identifiers are ignored. */
    @Transactional
    public void recordFailure(String normalisedIdentifier) {
        userRepository.findByUsernameOrEmail(normalisedIdentifier).ifPresent(user -> {
            int attempts = user.getFailedLoginAttempts() + 1;

            if (attempts >= properties.maxFailedAttempts()) {
                user.setFailedLoginAttempts(0);
                user.setLockedUntil(Instant.now().plus(properties.lockoutDuration()));
                log.warn("User id {} locked after {} failed login attempts", user.getId(), attempts);
            } else {
                user.setFailedLoginAttempts(attempts);
            }
        });
    }

    @Transactional
    public AppUser recordSuccess(Long userId) {
        AppUser user = userRepository.findById(userId).orElseThrow();
        user.setFailedLoginAttempts(0);
        user.setLockedUntil(null);
        user.setLastLoginAt(Instant.now());
        return user;
    }
}
