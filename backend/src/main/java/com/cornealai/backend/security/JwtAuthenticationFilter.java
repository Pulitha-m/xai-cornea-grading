package com.cornealai.backend.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.context.SecurityContextHolderStrategy;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Authenticates requests carrying an {@code Authorization: Bearer <jwt>} header.
 * <p>
 * An invalid token never short-circuits the chain: the request simply stays
 * anonymous, so protected endpoints answer 401 via the entry point while public
 * ones (e.g. login) keep working with a stale header.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    public static final String INVALID_TOKEN_ATTRIBUTE = JwtAuthenticationFilter.class.getName() + ".INVALID_TOKEN";

    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtService jwtService;
    private final AppUserDetailsService userDetailsService;
    private final SecurityContextHolderStrategy securityContextHolderStrategy =
            SecurityContextHolder.getContextHolderStrategy();
    private final WebAuthenticationDetailsSource detailsSource = new WebAuthenticationDetailsSource();

    public JwtAuthenticationFilter(JwtService jwtService, AppUserDetailsService userDetailsService) {
        this.jwtService = jwtService;
        this.userDetailsService = userDetailsService;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);

        if (header == null || !header.regionMatches(true, 0, BEARER_PREFIX, 0, BEARER_PREFIX.length())) {
            filterChain.doFilter(request, response);
            return;
        }

        String token = header.substring(BEARER_PREFIX.length()).trim();

        try {
            Jwt jwt = jwtService.decode(token);
            AppUserDetails user = userDetailsService.loadUserById(Long.valueOf(jwt.getSubject()));

            if (!user.isEnabled()) {
                throw new JwtException("Account disabled");
            }

            UsernamePasswordAuthenticationToken authentication =
                    UsernamePasswordAuthenticationToken.authenticated(user, null, user.getAuthorities());
            authentication.setDetails(detailsSource.buildDetails(request));

            SecurityContext context = securityContextHolderStrategy.createEmptyContext();
            context.setAuthentication(authentication);
            securityContextHolderStrategy.setContext(context);
        } catch (JwtException | AuthenticationException | IllegalArgumentException e) {
            // IllegalArgumentException covers a non-numeric subject (NumberFormatException)
            securityContextHolderStrategy.clearContext();
            request.setAttribute(INVALID_TOKEN_ATTRIBUTE, Boolean.TRUE);
        }

        filterChain.doFilter(request, response);
    }
}
