{{- define "platform-api.labels" -}}
app.kubernetes.io/name: platform-api
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: platform
{{- end }}

{{- define "platform-api.selectorLabels" -}}
app.kubernetes.io/name: platform-api
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
