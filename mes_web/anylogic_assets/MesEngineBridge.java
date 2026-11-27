import com.anylogic.engine.Engine;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import excel_test_konveyor.Main;
import excel_test_konveyor.Simulation;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

/** Controls the copied experiment over this process's private standard streams. */
public final class MesEngineBridge {
    private static final String PREFIX = "@MES@";

    private static void setSpeed(Engine engine, JsonNode speed) {
        int scale = speed.asInt();
        if (!speed.isIntegralNumber() || !speed.canConvertToInt() || (scale != 1 && scale != 2 && scale != 5 && scale != 10)) {
            throw new IllegalArgumentException("Geçersiz simülasyon hızı.");
        }
        if (!engine.getRealTimeMode()) engine.setRealTimeMode(true);
        engine.setRealTimeScale(scale);
    }

    private static void finish(Engine engine, Main model, ObjectMapper json) throws InterruptedException {
        Path path = Path.of(System.getProperty("mes.anylogic.runDir"), "live", "live-state.json");
        // Keep the publisher alive until the final event and inventory reach the same frame.
        for (int attempt = 0; attempt < 40; attempt++) {
            try {
                JsonNode frame = json.readTree(Files.readString(path));
                if (frame != null && frame.path("runId").asText().equals(model.live_run)) {
                    for (JsonNode event : frame.path("events")) {
                        if (event.path("message").asText().startsWith("TEST_SONUCU;;;")) {
                            if (engine.getState().toString().equals("RUNNING")) engine.pause();
                            return;
                        }
                    }
                }
            } catch (IOException ignored) {
                // The publisher may be replacing the frame between reads.
            }
            if (engine.getState().toString().equals("PAUSED")) engine.run();
            Thread.sleep(50);
        }
        throw new IllegalStateException("AnyLogic son model karesini kaydedemedi.");
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper json = new ObjectMapper();
        Simulation experiment = new Simulation();
        Engine engine = new Engine();
        boolean started = false;
        boolean completed = false;
        try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            engine.setExperiment(experiment);
            experiment.initDefaultRandomNumberGenerator(engine);
            experiment.setupEngine(engine);
            Main model = experiment.createRoot(engine);
            experiment.setupRootParameters(model, false);
            if (!engine.start(model)) throw new IllegalStateException("Model hazırlanamadı.");

            for (String line; (line = input.readLine()) != null;) {
                Map<String, Object> result = new LinkedHashMap<>();
                try {
                    JsonNode command = json.readTree(line);
                    String action = command.path("action").asText();
                    if (action.equals("start") && command.has("speed")) setSpeed(engine, command.path("speed"));
                    switch (action) {
                        case "start", "resume" -> {
                            if (!engine.run()) throw new IllegalStateException("Motor çalıştırılamadı.");
                            started = true;
                        }
                        case "pause" -> {
                            if (!engine.pause()) throw new IllegalStateException("Motor duraklatılamadı.");
                        }
                        case "speed" -> setSpeed(engine, command.path("speed"));
                        case "status" -> { }
                        case "shutdown" -> { return; }
                        default -> throw new IllegalArgumentException("Bilinmeyen komut.");
                    }
                    if (model.test_rapor_yazildi && !completed) {
                        finish(engine, model, json);
                        completed = true;
                    }
                    result.put("state", completed ? "completed" : switch (engine.getState().toString()) {
                        case "RUNNING" -> "running";
                        case "PAUSED" -> started ? "paused" : "ready";
                        default -> "error";
                    });
                    result.put("engineRunId", model.live_run);
                    result.put("modelTime", engine.time());
                    result.put("speed", engine.getRealTimeScale());
                    result.put("target", model.surekli_akis ? null : model.test_kimlikler.size());
                    result.put("verdict", model.test_rapor_yazildi ? model.test_durum : null);
                } catch (Exception error) {
                    result.put("error", error.toString());
                }
                System.out.println(PREFIX + json.writeValueAsString(result));
                System.out.flush();
            }
        } finally {
            engine.stop();
        }
        System.exit(0);
    }
}
