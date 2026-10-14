package com.cornealai.backend.security;

import com.cornealai.backend.user.repository.AppUserRepository;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Service
public class AppUserDetailsService implements UserDetailsService {

    private final AppUserRepository userRepository;

    public AppUserDetailsService(AppUserRepository userRepository) {
        this.userRepository = userRepository;
    }

    /** Loads a user by username or email (both stored lower-cased). */
    @Override
    @Transactional(readOnly = true)
    public AppUserDetails loadUserByUsername(String identifier) {
        return userRepository.findByUsernameOrEmail(normalise(identifier))
                .map(AppUserDetails::from)
                .orElseThrow(() -> new UsernameNotFoundException("User not found"));
    }

    @Transactional(readOnly = true)
    public AppUserDetails loadUserById(Long id) {
        return userRepository.findById(id)
                .map(AppUserDetails::from)
                .orElseThrow(() -> new UsernameNotFoundException("User not found"));
    }

    public static String normalise(String identifier) {
        return identifier == null ? "" : identifier.trim().toLowerCase(Locale.ROOT);
    }
}
