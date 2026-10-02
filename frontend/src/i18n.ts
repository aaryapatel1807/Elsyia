export const supportedLocales = ["en", "hi", "es", "fr", "de"] as const;
export type Locale = (typeof supportedLocales)[number];

type Messages = Record<string, string>;

const en: Messages = {
  "app.memory": "Memory · M",
  "app.plugins": "Plugins · P",
  "app.plans": "Plans · L",
  "app.agents": "Agents · A",
  "app.sync": "Sync · S",
  "app.admin": "Admin · E",
  "app.openMemory": "Open memory management",
  "app.openPlugins": "Open plugin management",
  "app.openPlans": "Open plan management",
  "app.openAgents": "Open agent management",
  "app.openSync": "Open local sync",
  "app.openAdmin": "Open enterprise administration",
  "app.hint": "HOLD SPACE TO TALK · ESC TO CANCEL · M FOR MEMORY · P FOR PLUGINS · L FOR PLANS · A FOR AGENTS · S FOR SYNC · E FOR ADMIN · DROP FILES",
  "app.confirmationRequired": "Confirmation required",
  "app.completed": "{tool} completed",
  "app.actionFailed": "Action failed",
  "language.title": "Language",
  "language.select": "Select language",
  "language.localOnly": "Language preference is stored on this device.",
  "language.english": "English",
  "language.hindi": "Hindi",
  "language.spanish": "Spanish",
  "language.french": "French",
  "language.german": "German",
  "panel.close": "Close",
};

const resources: Record<Locale, Messages> = {
  en,
  hi: {
    ...en,
    "app.memory": "मेमोरी · M",
    "app.plugins": "प्लगइन्स · P",
    "app.plans": "योजनाएँ · L",
    "app.agents": "एजेंट · A",
    "app.sync": "सिंक · S",
    "app.admin": "एडमिन · E",
    "app.openMemory": "मेमोरी प्रबंधन खोलें",
    "app.openPlugins": "प्लगइन प्रबंधन खोलें",
    "app.openPlans": "योजना प्रबंधन खोलें",
    "app.openAgents": "एजेंट प्रबंधन खोलें",
    "app.openSync": "स्थानीय सिंक खोलें",
    "app.openAdmin": "एंटरप्राइज़ प्रशासन खोलें",
    "app.hint": "बात करने के लिए SPACE दबाएँ · रद्द करने के लिए ESC · मेमोरी के लिए M · प्लगइन्स के लिए P · योजनाओं के लिए L · एजेंट के लिए A · सिंक के लिए S · एडमिन के लिए E · फ़ाइलें छोड़ें",
    "app.confirmationRequired": "पुष्टि आवश्यक है",
    "app.completed": "{tool} पूरा हुआ",
    "app.actionFailed": "कार्रवाई विफल हुई",
    "language.title": "भाषा",
    "language.select": "भाषा चुनें",
    "language.localOnly": "भाषा प्राथमिकता इसी डिवाइस पर संग्रहीत है।",
    "language.english": "अंग्रेज़ी",
    "language.hindi": "हिन्दी",
    "language.spanish": "स्पेनिश",
    "language.french": "फ़्रेंच",
    "language.german": "जर्मन",
    "panel.close": "बंद करें",
  },
  es: {
    ...en,
    "app.memory": "Memoria · M",
    "app.plugins": "Plugins · P",
    "app.plans": "Planes · L",
    "app.agents": "Agentes · A",
    "app.sync": "Sincronizar · S",
    "app.admin": "Admin · E",
    "app.openMemory": "Abrir gestión de memoria",
    "app.openPlugins": "Abrir gestión de plugins",
    "app.openPlans": "Abrir gestión de planes",
    "app.openAgents": "Abrir gestión de agentes",
    "app.openSync": "Abrir sincronización local",
    "app.openAdmin": "Abrir administración empresarial",
    "app.confirmationRequired": "Se requiere confirmación",
    "app.completed": "{tool} completado",
    "app.actionFailed": "La acción falló",
    "language.title": "Idioma",
    "language.select": "Seleccionar idioma",
    "language.localOnly": "La preferencia de idioma se guarda en este dispositivo.",
    "language.english": "Inglés",
    "language.hindi": "Hindi",
    "language.spanish": "Español",
    "language.french": "Francés",
    "language.german": "Alemán",
    "panel.close": "Cerrar",
  },
  fr: {
    ...en,
    "app.memory": "Mémoire · M",
    "app.plugins": "Plugins · P",
    "app.plans": "Plans · L",
    "app.agents": "Agents · A",
    "app.sync": "Synchroniser · S",
    "app.admin": "Admin · E",
    "app.openMemory": "Ouvrir la gestion de la mémoire",
    "app.openPlugins": "Ouvrir la gestion des plugins",
    "app.openPlans": "Ouvrir la gestion des plans",
    "app.openAgents": "Ouvrir la gestion des agents",
    "app.openSync": "Ouvrir la synchronisation locale",
    "app.openAdmin": "Ouvrir l’administration d’entreprise",
    "app.confirmationRequired": "Confirmation requise",
    "app.completed": "{tool} terminé",
    "app.actionFailed": "Échec de l’action",
    "language.title": "Langue",
    "language.select": "Choisir la langue",
    "language.localOnly": "La préférence de langue est stockée sur cet appareil.",
    "language.english": "Anglais",
    "language.hindi": "Hindi",
    "language.spanish": "Espagnol",
    "language.french": "Français",
    "language.german": "Allemand",
    "panel.close": "Fermer",
  },
  de: {
    ...en,
    "app.memory": "Speicher · M",
    "app.plugins": "Plugins · P",
    "app.plans": "Pläne · L",
    "app.agents": "Agenten · A",
    "app.sync": "Sync · S",
    "app.admin": "Admin · E",
    "app.openMemory": "Speicherverwaltung öffnen",
    "app.openPlugins": "Pluginverwaltung öffnen",
    "app.openPlans": "Planverwaltung öffnen",
    "app.openAgents": "Agentenverwaltung öffnen",
    "app.openSync": "Lokale Synchronisierung öffnen",
    "app.openAdmin": "Unternehmensverwaltung öffnen",
    "app.confirmationRequired": "Bestätigung erforderlich",
    "app.completed": "{tool} abgeschlossen",
    "app.actionFailed": "Aktion fehlgeschlagen",
    "language.title": "Sprache",
    "language.select": "Sprache auswählen",
    "language.localOnly": "Die Spracheinstellung wird auf diesem Gerät gespeichert.",
    "language.english": "Englisch",
    "language.hindi": "Hindi",
    "language.spanish": "Spanisch",
    "language.french": "Französisch",
    "language.german": "Deutsch",
    "panel.close": "Schließen",
  },
};

const STORAGE_KEY = "elysia.locale";

function normalizeLocale(value: string | null | undefined): Locale {
  const base = value?.toLowerCase().split("-")[0];
  return supportedLocales.includes(base as Locale) ? (base as Locale) : "en";
}

export function getStoredLocale(): Locale {
  try {
    return normalizeLocale(window.localStorage.getItem(STORAGE_KEY) || navigator.language);
  } catch {
    return "en";
  }
}

export function setStoredLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Local persistence is optional; the in-memory React state remains authoritative.
  }
}

export function translate(locale: Locale, key: string, values: Record<string, string | number> = {}): string {
  const template = resources[locale]?.[key] ?? resources.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_match, name: string) => String(values[name] ?? `{${name}}`));
}

export function formatDate(value: Date | number | string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function formatNumber(value: number, locale: Locale): string {
  return new Intl.NumberFormat(locale).format(value);
}

export const localeLabels: Record<Locale, string> = {
  en: "language.english",
  hi: "language.hindi",
  es: "language.spanish",
  fr: "language.french",
  de: "language.german",
};
