export interface DemoSample {
  id: string;
  title: string;
  eyebrow: string;
  sourceType: "text" | "ocr";
  text: string;
}

export const DEMO_SAMPLES: DemoSample[] = [
  {
    id: "s05-gurultu-sikayeti",
    title: "Gürültü şikâyeti",
    eyebrow: "Zabıta · tam başvuru",
    sourceType: "text",
    text: "Gece gürültü desibel rahatsızlık şikayet bildiriyorum. Başvuru sahibi Ayşe Yılmaz, T.C. Kimlik Numarası 10000000146. Olay adresi Atatürk Mahallesi 1. Sokak No: 2. Olay tarihi 25.08.2026. Olay açıklaması: Gece yüksek ses nedeniyle dinlenemiyoruz.",
  },
  {
    id: "s03-eksik-iletisim",
    title: "Eksik bilgi içeren dilekçe",
    eyebrow: "Vatandaş Hizmetleri · ek bilgi gerekli",
    sourceType: "ocr",
    text: "Talebimin değerlendirilmesini istiyorum. Başvuru metninde işlem için gereken iletişim ve destekleyici bilgiler eksiktir.",
  },
  {
    id: "s10-okunamayan-tarama",
    title: "İnceleme gereken tarama",
    eyebrow: "Belirsiz sınıflandırma · insan incelemesi",
    sourceType: "ocr",
    text: "Okunabilirliği düşük taranmış dilekçe içeriği belediye sınıflandırma kurallarında güvenilir bir eşleşme üretmemektedir.",
  },
  {
    id: "en-noise-complaint",
    title: "Noise complaint (English)",
    eyebrow: "Zabıta · English petition",
    sourceType: "text",
    text: "To the Municipality,\n\nI am a resident of Cumhuriyet neighborhood. For the past few weeks there has been continuous and disruptive noise from the business next door during night hours. The noise disturbs the quiet of our street and prevents sleep. I request an inspection and the necessary action under the licence conditions of this business.\n\nDate: 27.08.2026\nName: John Resident\nT.C. Kimlik No: 10000000146\nAddress: Cumhuriyet Mah. No: 12, Kadikoy/Istanbul\nPhone: 05551112233\n",
  },
];
