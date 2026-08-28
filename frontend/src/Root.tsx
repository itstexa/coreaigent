/**
 * Uygulama kabuğu: adrese göre hangi yüzeyin açılacağını seçer.
 *
 * Panel görünümü de buradan türetilir; `App` kendi içinde ikinci bir görünüm
 * state'i tutmaz, böylece geri tuşu ve yenileme adresle uyumlu kalır.
 */

import { useEffect, useState } from "react";
import { App } from "./App";
import { Landing } from "./Landing";
import { PetitionForm } from "./PetitionForm";
import { PetitionThanks } from "./PetitionThanks";
import { parseRoute } from "./router";

function useRoute() {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const sync = () => setPath(window.location.pathname);
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  return parseRoute(path);
}

export function Root() {
  const route = useRoute();
  switch (route.kind) {
    case "petition":
      return <PetitionForm />;
    case "thanks":
      return <PetitionThanks reference={route.reference} />;
    case "panel-overview":
      return <App view="overview" caseId={null} />;
    case "panel-queue":
      return <App view="queue" caseId={null} />;
    case "panel-intake":
      return <App view="new" caseId={null} />;
    case "panel-case":
      return <App view="case" caseId={route.caseId} />;
    default:
      return <Landing />;
  }
}
