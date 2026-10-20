package com.cornealai.backend.cases;

import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.DonorCaseRepository;
import com.cornealai.backend.common.crypto.BlindIndex;
import com.cornealai.backend.common.crypto.FieldCipher;
import com.cornealai.backend.support.IntegrationTestSupport;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** The V7 schema with the real crypto beans: sensitive fields reach the database only as ciphertext. */
class DonorCaseEncryptionIntegrationTests extends IntegrationTestSupport {

    @Autowired
    private DonorCaseRepository cases;

    @Autowired
    private FieldCipher cipher;

    @Autowired
    private BlindIndex blindIndex;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void sensitiveFieldsAreStoredEncryptedAndMeasurementsPlain() {
        AppUser nurse = createUser("nurse-cases", RoleName.NURSE);
        DonorCase saved = cases.saveAndFlush(newCase(nurse, "T-2023/045", "HIV negative; HBsAg negative"));

        Map<String, Object> row = jdbc.queryForMap(
                "SELECT tissue_number_enc, serology_enc, tissue_number_bidx, ecd FROM donor_cases WHERE id = ?",
                saved.getId());
        assertThat(text((byte[]) row.get("tissue_number_enc"))).doesNotContain("T-2023/045");
        assertThat(text((byte[]) row.get("serology_enc"))).doesNotContain("negative");
        assertThat((String) row.get("tissue_number_bidx")).doesNotContain("2023");
        assertThat(((Number) row.get("ecd")).doubleValue()).isEqualTo(2650.0);

        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM donor_cases WHERE ecd > 2500", Integer.class))
                .isEqualTo(1);
    }

    @Test
    void foundByTissueNumberThroughTheBlindIndexAndDecrypted() {
        AppUser nurse = createUser("nurse-lookup", RoleName.NURSE);
        DonorCase saved = cases.saveAndFlush(newCase(nurse, "T-2023/045", null));

        DonorCase found = cases.findByTissueNumberBidx(blindIndex.of(DonorCase.TISSUE_NUMBER_INDEX, " t-2023/045 "))
                .orElseThrow();
        assertThat(found.getId()).isEqualTo(saved.getId());
        assertThat(cipher.decrypt(found.getTissueNumberEnc(), DonorCase.TISSUE_NUMBER, found.getId()))
                .isEqualTo("T-2023/045");
        assertThat(found.getSerologyEnc()).isNull();
    }

    @Test
    void sameTissueNumberCannotBeRegisteredTwice() {
        AppUser nurse = createUser("nurse-duplicate", RoleName.NURSE);
        cases.saveAndFlush(newCase(nurse, "T-2023/045", null));
        assertThatThrownBy(() -> cases.saveAndFlush(newCase(nurse, "t-2023/045", null)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    private DonorCase newCase(AppUser createdBy, String tissueNumber, String serology) {
        DonorCase c = new DonorCase();
        c.setId(UUID.randomUUID());
        c.setTissueNumberEnc(cipher.encrypt(tissueNumber, DonorCase.TISSUE_NUMBER, c.getId()));
        c.setTissueNumberBidx(blindIndex.of(DonorCase.TISSUE_NUMBER_INDEX, tissueNumber));
        c.setSerologyEnc(cipher.encrypt(serology, DonorCase.SEROLOGY, c.getId()));
        c.setSerologyClear(serology == null ? null : true);
        c.setDonorAgeYears(54);
        c.setEcd(2650.0);
        c.setCv(32.0);
        c.setHexPercent(58.0);
        c.setCreatedBy(createdBy.getId());
        return c;
    }

    private static String text(byte[] bytes) {
        return new String(bytes, StandardCharsets.ISO_8859_1);
    }
}
