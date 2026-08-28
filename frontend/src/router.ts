/**
 * Yol tabanlı (path) yönlendirme.
 *
 * Uygulama artık üç ayrı yüzey barındırıyor: herkese açık tanıtım sayfası,
 * vatandaşın dilekçe yazdığı portal ve operatör paneli.  nginx yapılandırması
 * `try_files $uri $uri/ /index.html` içerdiği için sunucu tarafında ayrı bir
 * kural gerekmez; tarayıcı hangi adrese girerse girsin index.html yüklenir ve
 * ayrımı burası yapar.
 *
 * Panel görünümleri de adresten türetilir; böylece geri tuşu, yenileme ve
 * paylaşılan bağlantı beklendiği gibi çalışır ve React tarafında adresle
 * çelişebilecek ikinci bir görünüm state'i tutulmaz.
 */

export type Route =
  | { kind: "landing" }
  | { kind: "petition" }
  | { kind: "thanks"; reference: string }
  | { kind: "panel-overview" }
  | { kind: "panel-queue" }
  | { kind: "panel-intake" }
  | { kind: "panel-case"; caseId: string };

export const PATHS = {
  landing: "/",
  petition: "/dilekce",
  panel: "/panel",
  panelQueue: "/panel/dosyalar",
  panelIntake: "/panel/yeni",
} as const;

export function thanksPath(reference: string): string {
  return `/dilekce/tesekkurler/${encodeURIComponent(reference)}`;
}

export function casePath(caseId: string): string {
  return `/panel/dosya/${encodeURIComponent(caseId)}`;
}

function decode(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    // Bozuk yüzde kodlaması adresin tamamını çöpe atmamalı; segment ham
    // hâliyle kullanılır ve isteği backend reddeder.
    return segment;
  }
}

/** Adresi bilinen bir görünüme çevirir; tanınmayan her yol tanıtım sayfasıdır. */
export function parseRoute(pathname: string): Route {
  const parts = pathname.split("/").filter(Boolean).map(decode);
  if (parts.length === 0) return { kind: "landing" };
  if (parts[0] === "dilekce") {
    if (parts.length === 1) return { kind: "petition" };
    if (parts[1] === "tesekkurler" && parts.length === 3) return { kind: "thanks", reference: parts[2] };
    return { kind: "petition" };
  }
  if (parts[0] === "panel") {
    if (parts.length === 1) return { kind: "panel-overview" };
    if (parts[1] === "dosyalar" && parts.length === 2) return { kind: "panel-queue" };
    if (parts[1] === "yeni") return { kind: "panel-intake" };
    if (parts[1] === "dosya" && parts.length === 3) return { kind: "panel-case", caseId: parts[2] };
    return { kind: "panel-overview" };
  }
  return { kind: "landing" };
}

export function navigate(path: string): void {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0 });
}
