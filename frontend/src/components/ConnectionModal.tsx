import { useEffect, useState } from "react";
import {
  type ConfigSnapshot,
  getConfig,
  reloadConfig,
  testGemini,
} from "../lib/api";

interface Props {
  onClose: () => void;
}

interface PingResult {
  ok: boolean;
  reply?: string;
  error?: string;
}

export function ConnectionModal({ onClose }: Props) {
  const [config, setConfig] = useState<ConfigSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"reload" | "ping" | null>(null);
  const [ping, setPing] = useState<PingResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const onReload = async () => {
    setBusy("reload");
    setErr(null);
    try {
      const fresh = await reloadConfig();
      setConfig(fresh);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const onPing = async () => {
    setBusy("ping");
    setPing(null);
    try {
      setPing(await testGemini());
    } catch (e) {
      setPing({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-xl w-[640px] max-w-[92vw] max-h-[85vh] border border-gray-200 flex flex-col">
        <header className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-navy font-semibold">Conectar con instancia</h2>
            <p className="text-xs text-gray-secondary mt-1">
              Credenciales actuales (cargadas desde <code className="font-mono">.env</code>).
              Edita el archivo y pulsa <strong>Recargar .env</strong>.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-secondary hover:text-navy text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="px-5 py-4 overflow-y-auto flex-1">
          {loading && <p className="text-sm text-gray-secondary">Cargando…</p>}
          {err && (
            <p className="text-sm text-danger mb-3">{err}</p>
          )}
          {config && (
            <div className="space-y-5 text-sm">
              <section>
                <h3 className="text-navy font-semibold mb-2 text-xs uppercase tracking-wide">
                  SAP SuccessFactors
                </h3>
                <table className="w-full text-xs">
                  <tbody>
                    {[
                      ["API host", config.sf.api_host],
                      ["Company ID", config.sf.company_id],
                      ["User ID", config.sf.user_id],
                      ["Password", config.sf.password_masked],
                      ["IAS host", config.sf.ias_host],
                      ["OIDC Client ID", config.sf.oidc_client_id],
                      ["OIDC Client Secret", config.sf.oidc_client_secret_masked],
                      ["IAS dependency", config.sf.ias_dependency_name],
                    ].map(([k, v]) => (
                      <tr key={k} className="border-b border-gray-100 last:border-0">
                        <td className="py-1.5 text-gray-secondary w-44">{k}</td>
                        <td className="py-1.5 font-mono break-all">{v || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section>
                <h3 className="text-navy font-semibold mb-2 text-xs uppercase tracking-wide">
                  Gemini
                </h3>
                <table className="w-full text-xs">
                  <tbody>
                    <tr className="border-b border-gray-100">
                      <td className="py-1.5 text-gray-secondary w-44">API key</td>
                      <td className="py-1.5 font-mono break-all">
                        {config.gemini.api_key_masked || "—"}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-1.5 text-gray-secondary w-44">Model</td>
                      <td className="py-1.5 font-mono">{config.gemini.model}</td>
                    </tr>
                  </tbody>
                </table>
              </section>

              {ping && (
                <section
                  className={`rounded p-3 text-xs ${
                    ping.ok
                      ? "bg-success/10 border border-success/30 text-success"
                      : "bg-danger/10 border border-danger/30 text-danger"
                  }`}
                >
                  {ping.ok ? (
                    <>
                      Gemini respondió: <code className="font-mono">{ping.reply}</code>
                    </>
                  ) : (
                    <>Gemini error: {ping.error}</>
                  )}
                </section>
              )}
            </div>
          )}
        </div>

        <footer className="px-5 py-3 border-t border-gray-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onPing}
            disabled={busy !== null}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-bg-soft disabled:opacity-50"
          >
            {busy === "ping" ? "Probando…" : "Probar Gemini"}
          </button>
          <button
            type="button"
            onClick={onReload}
            disabled={busy !== null}
            className="px-3 py-1.5 text-sm bg-success text-white rounded hover:opacity-90 disabled:opacity-50"
          >
            {busy === "reload" ? "Recargando…" : "Recargar .env"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm bg-navy text-white rounded hover:bg-navy-dark"
          >
            Cerrar
          </button>
        </footer>
      </div>
    </div>
  );
}
