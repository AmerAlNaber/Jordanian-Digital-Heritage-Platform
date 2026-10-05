package jo.jdhp.keycloak.password;

import java.time.Duration;
import java.util.function.IntSupplier;
import org.keycloak.Config;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.PasswordPolicy;
import org.keycloak.models.RealmModel;
import org.keycloak.policy.PasswordPolicyProvider;
import org.keycloak.policy.PasswordPolicyProviderFactory;

/** Registers the {@code breachedPassword} policy; configured by environment (SEC-19). */
public final class BreachedPasswordPolicyProviderFactory implements PasswordPolicyProviderFactory {

    public static final String ID = "breachedPassword";
    static final String ENV_RANGE_URL = "JDHP_PWNED_RANGE_URL";
    static final String ENV_FAIL_CLOSED = "JDHP_BREACHED_PASSWORD_FAIL_CLOSED";
    private static final Duration TIMEOUT = Duration.ofSeconds(5);

    private PwnedRangeClient client;
    private boolean failClosed;

    @Override
    public PasswordPolicyProvider create(KeycloakSession session) {
        IntSupplier threshold = () -> {
            RealmModel realm = session.getContext() == null ? null : session.getContext().getRealm();
            PasswordPolicy policy = realm == null ? null : realm.getPasswordPolicy();
            Integer configured = policy == null ? null : policy.getPolicyConfig(ID);
            return configured == null ? BreachedPasswordPolicyProvider.DEFAULT_THRESHOLD : configured;
        };
        return new BreachedPasswordPolicyProvider(client, failClosed, threshold);
    }

    @Override
    public void init(Config.Scope config) {
        String url = System.getenv().getOrDefault(ENV_RANGE_URL, PwnedRangeClient.DEFAULT_RANGE_URL);
        failClosed = Boolean.parseBoolean(System.getenv().getOrDefault(ENV_FAIL_CLOSED, "false"));
        client = new PwnedRangeClient(url, TIMEOUT);
    }

    @Override
    public void postInit(KeycloakSessionFactory factory) {
        // nothing to wire
    }

    @Override
    public void close() {
        // nothing to release
    }

    @Override
    public String getId() {
        return ID;
    }

    @Override
    public String getDisplayName() {
        return "Breached password (k-anonymity range check)";
    }

    @Override
    public String getConfigType() {
        return PasswordPolicyProvider.INT_CONFIG_TYPE;
    }

    @Override
    public String getDefaultConfigValue() {
        return String.valueOf(BreachedPasswordPolicyProvider.DEFAULT_THRESHOLD);
    }

    @Override
    public boolean isMultiplSupported() {
        return false;
    }
}
