FROM golang:1.27.4-bookworm@sha256:fb7cceb528b47141eccd9b60bf3cbd27d5ef5f8cf5b7d338bec866da495b50dc AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/workflows-scaffold ./cmd/workflows-scaffold

FROM gcr.io/distroless/static-debian13:nonroot@sha256:816dc4d589459a7fe33b8a2e69edb70da56ffad7161f4b415937fa2bfe7e92e8
COPY --from=build /out/workflows-scaffold /usr/local/bin/workflows-scaffold
ENV SCAFFOLD_HTTP=true
EXPOSE 8080
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/workflows-scaffold"]
