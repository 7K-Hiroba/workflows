{{- define "workflows-scaffold.fullname" -}}
{{ .Release.Name }}
{{- end }}
{{- define "workflows-scaffold.labels" -}}
app.kubernetes.io/name: workflows-scaffold
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
