package com.cornealai.backend.user.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "roles")
@Getter
@NoArgsConstructor
public class Role {

    @Id
    private Integer id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, unique = true, length = 32)
    private RoleName name;

    @Column(nullable = false)
    private String description;
}
