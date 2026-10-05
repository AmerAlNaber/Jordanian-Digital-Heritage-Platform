package jo.jdhp.keycloak.password;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Locale;

/**
 * k-anonymity lookup against a Pwned Passwords style range API (SEC-4, ACC-1).
 *
 * <p>Only the first five hex characters of the password's SHA-1 leave the server; the
 * response lists every suffix in that range and the match is made locally. Padding is
 * requested so the response size does not reveal the range.
 */
public final class PwnedRangeClient {

    public static final String DEFAULT_RANGE_URL = "https://api.pwnedpasswords.com/range";
    private static final int PREFIX_LENGTH = 5;

    private final HttpClient http;
    private final String baseUrl;
    private final Duration timeout;

    public PwnedRangeClient(String baseUrl, Duration timeout) {
        this.baseUrl = stripTrailingSlash(baseUrl);
        this.timeout = timeout;
        this.http = HttpClient.newBuilder()
                .connectTimeout(timeout)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    /** How many times the password appears in the breach corpus; zero when it does not. */
    public int breachCount(String password) throws IOException, InterruptedException {
        String digest = sha1Hex(password);
        String prefix = digest.substring(0, PREFIX_LENGTH);
        String suffix = digest.substring(PREFIX_LENGTH);
        HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + "/" + prefix))
                .timeout(timeout)
                .header("Add-Padding", "true")
                .header("User-Agent", "jdhp-keycloak-extensions")
                .GET()
                .build();
        HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IOException("range API answered HTTP " + response.statusCode());
        }
        return parseCount(response.body(), suffix);
    }

    static int parseCount(String body, String suffix) {
        for (String line : body.split("\\r?\\n")) {
            int colon = line.indexOf(':');
            if (colon < 0) {
                continue;
            }
            if (line.substring(0, colon).trim().equalsIgnoreCase(suffix)) {
                try {
                    return Integer.parseInt(line.substring(colon + 1).trim());
                } catch (NumberFormatException e) {
                    return 0;
                }
            }
        }
        return 0;
    }

    static String sha1Hex(String password) {
        try {
            MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
            byte[] digest = sha1.digest(password.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).toUpperCase(Locale.ROOT);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-1 is required by the range API", e);
        }
    }

    private static String stripTrailingSlash(String url) {
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }
}
