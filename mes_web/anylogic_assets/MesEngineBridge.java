import com.anylogic.engine.Engine;
import com.fasterxml.jackson.databind.ObjectMapper;
import excel_test_konveyor.Main;
import excel_test_konveyor.Simulation;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/** Controls the copied experiment over this process's private standard streams. */
public final class MesEngineBridge {
    private static final String PREFIX = "@MES@";

    public static void main(String[] args) throws Exception {
        ObjectMapper json = new ObjectMapper();
        Simulation experiment = new Simulation();
        Engine engine = new Engine();
        boolean started = false;
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
                    String action = json.readTree(line).path("action").asText();
                    switch (action) {
                        case "start", "resume" -> {
                            if (!engine.run()) throw new IllegalStateException("Motor çalıştırılamadı.");
                            started = true;
                        }
                        case "pause" -> {
                            if (!engine.pause()) throw new IllegalStateException("Motor duraklatılamadı.");
                        }
                        case "status" -> { }
                        case "shutdown" -> { return; }
                        default -> throw new IllegalArgumentException("Bilinmeyen komut.");
                    }
                    String engineState = engine.getState().toString();
                    if (model.test_rapor_yazildi && engineState.equals("RUNNING")) {
                        engine.pause();
                        engineState = engine.getState().toString();
                    }
                    result.put("state", model.test_rapor_yazildi ? "completed" : switch (engineState) {
                        case "RUNNING" -> "running";
                        case "PAUSED" -> started ? "paused" : "ready";
                        default -> "error";
                    });
                    result.put("engineRunId", model.live_run);
                    result.put("modelTime", engine.time());
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
