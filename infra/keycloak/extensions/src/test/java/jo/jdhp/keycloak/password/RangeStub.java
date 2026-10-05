package jo.jdhp.keycloak.password;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** A range API on localhost: answers from a map of prefix to body, or a fixed status. */
final class RangeStub implements AutoCloseable {

    private final HttpServer server;
    final List<String> paths = new ArrayList<>();
    final List<String> paddingHeaders = new ArrayList<>();

    RangeStub(Map<String, String> bodiesByPrefix, int status) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/range", exchange -> {
            String path = exchange.getRequestURI().getPath();
            paths.add(path);
            paddingHeaders.add(exchange.getRequestHeaders().getFirst("Add-Padding"));
            String prefix = path.substring(path.lastIndexOf('/') + 1);
            String body = bodiesByPrefix.getOrDefault(prefix, "");
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();
    }

    String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort() + "/range";
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
