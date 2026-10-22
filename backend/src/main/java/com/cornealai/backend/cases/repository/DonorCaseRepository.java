package com.cornealai.backend.cases.repository;

import com.cornealai.backend.cases.entity.DonorCase;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface DonorCaseRepository extends JpaRepository<DonorCase, UUID> {

    /** Look up by tissue number through its blind index: {@code blindIndex.of(DonorCase.TISSUE_NUMBER_INDEX, number)}. */
    Optional<DonorCase> findByTissueNumberBidx(String tissueNumberBidx);

    /** Many cases in one query, by their blind indexes (bulk import). */
    List<DonorCase> findByTissueNumberBidxIn(Collection<String> tissueNumberBidxs);

    List<DonorCase> findTop20ByOrderByUpdatedAtDesc();
}
