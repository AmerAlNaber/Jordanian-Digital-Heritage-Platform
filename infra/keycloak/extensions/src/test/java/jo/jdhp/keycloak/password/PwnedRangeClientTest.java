package jo.jdhp.keycloak.password;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import org.junit.jupiter.api.Test;

class PwnedRangeClientTest {

    private static final String PASSWORD = "password";
    private static final String DIGEST = "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8";

    @Test
    void sha1_matches_the_published_digest() {
        assertEquals(DIGEST, PwnedRangeClient.sha1Hex(PASSWORD));
    }

    @Test
    void sec_4_only_the_five_character_prefix_leaves_the_server_and_padding_is_requested() throws Exception {
        String body = "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n"
                + DIGEST.substring(5).toLowerCase() + ":3861493\r\n"
                + "011053FD0102E94D6AE2F8B83D76FAF94F6:0\r\n";
        try (RangeStub stub = new RangeStub(Map.of("5BAA6", body), 200)) {
            PwnedRangeClient client = new PwnedRangeClient(stub.url(), Duration.ofSeconds(2));
            assertEquals(3861493, client.breachCount(PASSWORD));
            assertEquals("/range/5BAA6", stub.paths.get(0));
            assertEquals("true", stub.paddingHeaders.get(0));
        }
    }

    @Test
    void a_suffix_absent_from_the_range_counts_zero() throws Exception {
        String body = "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n";
        try (RangeStub stub = new RangeStub(Map.of("5BAA6", body), 200)) {
            PwnedRangeClient client = new PwnedRangeClient(stub.url(), Duration.ofSeconds(2));
            assertEquals(0, client.breachCount(PASSWORD));
        }
    }

    @Test
    void a_non_200_answer_is_an_error_not_a_clean_password() throws Exception {
        try (RangeStub stub = new RangeStub(Map.of(), 503)) {
            PwnedRangeClient client = new PwnedRangeClient(stub.url(), Duration.ofSeconds(2));
            assertThrows(IOException.class, () -> client.breachCount(PASSWORD));
        }
    }

    @Test
    void malformed_lines_are_ignored() {
        assertEquals(7, PwnedRangeClient.parseCount("garbage\nABC:7\n", "abc"));
        assertEquals(0, PwnedRangeClient.parseCount("ABC:not-a-number\n", "ABC"));
    }
}
