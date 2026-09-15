import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { applyDocumentMeta, documentMeta } from './documentMeta'

/** Keeps the tab title, canonical link and robots meta in step with the route
 * and the language. The document head is outside React, which is what the
 * effect is for. */
export function useDocumentMeta(path: string) {
  const { t, i18n } = useTranslation()
  const { title, indexable, canonical } = documentMeta(path, t, i18n.language)
  useEffect(() => {
    applyDocumentMeta({ title, indexable, canonical })
  }, [title, indexable, canonical])
}
