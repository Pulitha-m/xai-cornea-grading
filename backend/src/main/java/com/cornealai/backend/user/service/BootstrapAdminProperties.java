package com.cornealai.backend.user.service;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.bootstrap.admin")
public record BootstrapAdminProperties(
        String email,
        String username,
        String password,
        String fullName
) {

    public boolean isConfigured() {
        return email != null && !email.isBlank() && password != null && !password.isBlank();
    }
}
