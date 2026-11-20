{{- define "hiroba-nonplugin-smoke.fullname" -}}
{{ .Release.Name }}
{{- end }}
{{- define "hiroba-nonplugin-smoke.labels" -}}
app.kubernetes.io/name: hiroba-nonplugin-smoke
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
