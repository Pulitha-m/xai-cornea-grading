package com.cornealai.backend.user.controller;

import com.cornealai.backend.security.AppUserDetails;
import com.cornealai.backend.user.dto.*;
import com.cornealai.backend.user.service.UserService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('users:read')")
    public List<UserResponse> listUsers() {
        return userService.listUsers();
    }

    /** Creating an account assigns its role, so both permissions are required. */
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @PreAuthorize("hasAuthority('users:manage') and hasAuthority('roles:assign')")
    public UserResponse createUser(@Valid @RequestBody CreateUserRequest request) {
        return userService.createUser(request);
    }

    @PutMapping("/{id}/role")
    @PreAuthorize("hasAuthority('roles:assign')")
    public UserResponse assignRole(
            @PathVariable Long id,
            @Valid @RequestBody UpdateRoleRequest request,
            @AuthenticationPrincipal AppUserDetails principal
    ) {
        return userService.assignRole(id, request.role(), principal.getId());
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAuthority('users:manage')")
    public UserResponse updateStatus(
            @PathVariable Long id,
            @Valid @RequestBody UpdateStatusRequest request,
            @AuthenticationPrincipal AppUserDetails principal
    ) {
        return userService.setEnabled(id, request.enabled(), principal.getId());
    }

    @PutMapping("/{id}/password")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @PreAuthorize("hasAuthority('users:manage')")
    public void resetPassword(
            @PathVariable Long id,
            @Valid @RequestBody ResetPasswordRequest request,
            @AuthenticationPrincipal AppUserDetails principal
    ) {
        userService.resetPassword(id, request.newPassword(), principal.getId());
    }
}
