package com.cornealai.backend.user.service;

import com.cornealai.backend.user.dto.CreateUserRequest;
import com.cornealai.backend.user.entity.RoleName;
import com.cornealai.backend.user.repository.AppUserRepository;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import java.util.Set;
import java.util.stream.Collectors;

/**
 * Creates the first administrator from BOOTSTRAP_ADMIN_* environment variables,
 * but only while no ADMIN account exists. Remove the variables after first start.
 */
@Component
public class AdminBootstrapRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AdminBootstrapRunner.class);

    private final BootstrapAdminProperties properties;
    private final AppUserRepository userRepository;
    private final UserService userService;
    private final Validator validator;

    public AdminBootstrapRunner(
            BootstrapAdminProperties properties,
            AppUserRepository userRepository,
            UserService userService,
            Validator validator
    ) {
        this.properties = properties;
        this.userRepository = userRepository;
        this.userService = userService;
        this.validator = validator;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!properties.isConfigured()) {
            return;
        }

        if (userRepository.existsByRole_Name(RoleName.ADMIN)) {
            log.warn("An administrator already exists; ignoring BOOTSTRAP_ADMIN_* settings. "
                    + "Remove BOOTSTRAP_ADMIN_PASSWORD from the environment.");
            return;
        }

        CreateUserRequest request = new CreateUserRequest(
                properties.username(),
                properties.email(),
                properties.fullName(),
                RoleName.ADMIN,
                properties.password()
        );

        Set<ConstraintViolation<CreateUserRequest>> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            String problems = violations.stream()
                    .map(v -> v.getPropertyPath() + " " + v.getMessage())
                    .collect(Collectors.joining(", "));
            throw new IllegalStateException("Invalid BOOTSTRAP_ADMIN_* configuration: " + problems);
        }

        userService.createUser(request);
        log.warn("Bootstrap administrator '{}' created. Remove BOOTSTRAP_ADMIN_PASSWORD from the environment now.",
                properties.username());
    }
}
