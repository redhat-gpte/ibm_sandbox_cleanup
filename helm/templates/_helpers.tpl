{{/*
Expand the name of the chart.
*/}}
{{- define "ibm-sandbox-cleanup.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create the name of the namespace to use
*/}}
{{- define "ibm-sandbox-cleanup.namespaceName" -}}
{{- include "ibm-sandbox-cleanup.name" . }}
{{- end -}}


{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "ibm-sandbox-cleanup.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if (eq .Release.Name "RELEASE-NAME") }}
{{- $name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "ibm-sandbox-cleanup.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ibm-sandbox-cleanup.labels" -}}
helm.sh/chart: {{ include "ibm-sandbox-cleanup.chart" . }}
{{ include "ibm-sandbox-cleanup.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ibm-sandbox-cleanup.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ibm-sandbox-cleanup.name" . }}
{{- if (ne .Release.Name "RELEASE-NAME") }}
app.kubernetes.io/instance: {{ include "ibm-sandbox-cleanup.name" . }}
{{- end -}}
{{- end }}
