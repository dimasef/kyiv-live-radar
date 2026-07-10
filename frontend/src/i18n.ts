import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import uk from './locales/uk.json'

const STORAGE_KEY = 'klr-lang'

function initialLang(): string {
  return localStorage.getItem(STORAGE_KEY) ?? 'uk'
}

i18n.use(initReactI18next).init({
  resources: { uk: { translation: uk }, en: { translation: en } },
  lng: initialLang(),
  fallbackLng: 'uk',
  interpolation: { escapeValue: false },
})

export function setLanguage(lng: string) {
  localStorage.setItem(STORAGE_KEY, lng)
  i18n.changeLanguage(lng)
}

export default i18n
