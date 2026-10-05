package jo.jdhp.keycloak.password;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.keycloak.policy.PasswordPolicyConfigException;
import org.keycloak.policy.PolicyError;

class BreachedPasswordPolicyProviderTest {

    private static final String BREACHED = "password";
    private static final String CLEAN = "correct horse battery staple 2026";

    private static Map<String, String> corpus() {
        String breachedSuffix = PwnedRangeClient.sha1Hex(BREACHED).substring(5);
        String cleanPrefix = PwnedRangeClient.sha1Hex(CLEAN).substring(0, 5);
        return Map.of(
                "5BAA6", "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n" + breachedSuffix + ":3861493\r\n",
                cleanPrefix, "0000000000000000000000000000000000A:2\r\n");
    }

    @Test
    void sec_4_breached_password_rejected() throws Exception {
        try (RangeStub stub = new RangeStub(corpus(), 200)) {
            PwnedRangeClient client = new PwnedRangeClient(stub.url(), Duration.ofSeconds(2));
            BreachedPasswordPolicyProvider provider = new BreachedPasswordPolicyProvider(client, false, () -> 0);
            PolicyError error = provider.validate("someone", BREACHED);
            assertNotNull(error);
            assertEquals(BreachedPasswordPolicyProvider.MESSAGE_BREACHED, error.getMessage());
            assertNull(provider.validate("someone", CLEAN));
        }
    }

    @Test
    void the_threshold_is_the_number_of_sightings_still_accepted() throws Exception {
        try (RangeStub stub = new RangeStub(corpus(), 200)) {
            PwnedRangeClient client = new PwnedRangeClient(stub.url(), Duration.ofSeconds(2));
            assertNull(new BreachedPasswordPolicyProvider(client, false, () -> 3861493).validate("u", BREACHED));
            assertNotNull(new BreachedPasswordPolicyProvider(client, false, () -> 3861492).validate("u", BREACHED));
        }
    }

    @Test
    void an_unreachable_range_api_fails_open_by_default_and_closed_on_request() {
        PwnedRangeClient dead = new PwnedRangeClient("http://127.0.0.1:9/range", Duration.ofMillis(500));
        assertNull(new BreachedPasswordPolicyProvider(dead, false, () -> 0).validate("u", CLEAN));
        PolicyError error = new BreachedPasswordPolicyProvider(dead, true, () -> 0).validate("u", CLEAN);
        assertNotNull(error);
        assertEquals(BreachedPasswordPolicyProvider.MESSAGE_UNAVAILABLE, error.getMessage());
    }

    @Test
    void an_empty_password_is_left_to_the_length_policy() {
        PwnedRangeClient dead = new PwnedRangeClient("http://127.0.0.1:9/range", Duration.ofMillis(500));
        assertNull(new BreachedPasswordPolicyProvider(dead, true, () -> 0).validate("u", ""));
        assertNull(new BreachedPasswordPolicyProvider(dead, true, () -> 0).validate("u", null));
    }

    @Test
    void the_policy_argument_is_an_integer_with_zero_as_default() {
        PwnedRangeClient dead = new PwnedRangeClient("http://127.0.0.1:9/range", Duration.ofMillis(500));
        BreachedPasswordPolicyProvider provider = new BreachedPasswordPolicyProvider(dead, false, () -> 0);
        assertEquals(0, provider.parseConfig(null));
        assertEquals(0, provider.parseConfig(""));
        assertEquals(5, provider.parseConfig(" 5 "));
        assertThrows(PasswordPolicyConfigException.class, () -> provider.parseConfig("many"));
        assertThrows(PasswordPolicyConfigException.class, () -> provider.parseConfig("-1"));
    }
}
