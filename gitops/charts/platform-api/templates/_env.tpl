{{/* Environment shared by the api and worker containers. */}}
{{- define "platform-api.env" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.database.secretName }}
      key: {{ .Values.database.uriKey }}
- name: PLATFORM_GITHUB_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.github.secretName }}
      key: {{ .Values.github.tokenKey }}
      optional: true
- name: GITHUB_REPO
  value: {{ .Values.github.repo | quote }}
- name: GITHUB_BASE_BRANCH
  value: {{ .Values.github.baseBranch | quote }}
- name: PLATFORM_ENVIRONMENT
  value: local
{{- end }}
