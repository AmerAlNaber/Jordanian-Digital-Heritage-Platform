package jo.jdhp.keycloak.password;

import java.io.IOException;
import java.util.function.IntSupplier;
import org.jboss.logging.Logger;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;
import org.keycloak.policy.PasswordPolicyConfigException;
import org.keycloak.policy.PasswordPolicyProvider;
import org.keycloak.policy.PolicyError;

/**
 * Password policy {@code breachedPassword(n)}: refuse a password seen more than {@code n}
 * times in the breach corpus, at registration, reset and change alike (SEC-4, ACC-1).
 *
 * <p>When the range API cannot be reached the policy fails open by default and logs a
 * warning, because an outage of a third party must not stop registration; deployments that
 * prefer to refuse set {@code JDHP_BREACHED_PASSWORD_FAIL_CLOSED=true} (ADR-0009). Neither
 * the password nor the user is ever logged.
 */
public final class BreachedPasswordPolicyProvider implements PasswordPolicyProvider {

    static final String MESSAGE_BREACHED = "invalidPasswordBreachedMessage";
    static final String MESSAGE_UNAVAILABLE = "invalidPasswordCheckUnavailableMessage";
    static final int DEFAULT_THRESHOLD = 0;

    private static final Logger LOG = Logger.getLogger(BreachedPasswordPolicyProvider.class);

    private final PwnedRangeClient client;
    private final boolean failClosed;
    private final IntSupplier threshold;

    public BreachedPasswordPolicyProvider(PwnedRangeClient client, boolean failClosed, IntSupplier threshold) {
        this.client = client;
        this.failClosed = failClosed;
        this.threshold = threshold;
    }

    @Override
    public PolicyError validate(RealmModel realm, UserModel user, String password) {
        return validate(user == null ? null : user.getUsername(), password);
    }

    @Override
    public PolicyError validate(String username, String password) {
        if (password == null || password.isEmpty()) {
            return null; // the length policy answers for empty passwords
        }
        int allowed = threshold.getAsInt();
        try {
            return client.breachCount(password) > allowed ? new PolicyError(MESSAGE_BREACHED) : null;
        } catch (IOException e) {
            return unavailable(e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return unavailable("interrupted");
        }
    }

    private PolicyError unavailable(String reason) {
        LOG.warnf("breached-password check unavailable (%s): %s", reason,
                failClosed ? "refusing the password" : "accepting without the check");
        return failClosed ? new PolicyError(MESSAGE_UNAVAILABLE) : null;
    }

    /** The policy argument: how many sightings are still tolerated; blank means none. */
    @Override
    public Object parseConfig(String value) {
        if (value == null || value.isBlank()) {
            return DEFAULT_THRESHOLD;
        }
        try {
            int threshold = Integer.parseInt(value.trim());
            if (threshold < 0) {
                throw new PasswordPolicyConfigException("Must be zero or more");
            }
            return threshold;
        } catch (NumberFormatException e) {
            throw new PasswordPolicyConfigException("Not a valid number");
        }
    }

    @Override
    public void close() {
        // the HTTP client is shared by the factory
    }
}
