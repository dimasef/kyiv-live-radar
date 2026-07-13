import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from './lib/storage'
import en from './locales/en.json'
import uk from './locales/uk.json'

function initialLang(): string {
  return safeGet(STORAGE_KEYS.lang) ?? 'uk'
}

i18n.use(initReactI18next).init({
  resources: { uk: { translation: uk }, en: { translation: en } },
  lng: initialLang(),
  fallbackLng: 'uk',
  interpolation: { escapeValue: false },
})

export function setLanguage(lng: string) {
  safeSet(STORAGE_KEYS.lang, lng)
  i18n.changeLanguage(lng)
}

export default i18n
