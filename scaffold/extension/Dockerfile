FROM golang:1.26.3-bookworm@sha256:3bf5b04541eb4a37fe62aa1bc9c98a1dec09db9d2e79c1d2eb54e3c9d08dbca9 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/workflows-scaffold ./cmd/workflows-scaffold

FROM gcr.io/distroless/static-debian13:nonroot@sha256:816dc4d589459a7fe33b8a2e69edb70da56ffad7161f4b415937fa2bfe7e92e8
COPY --from=build /out/workflows-scaffold /usr/local/bin/workflows-scaffold
ENV SCAFFOLD_HTTP=true
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/workflows-scaffold"]
