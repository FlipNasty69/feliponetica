# Feliponetica Word API

The private Word transcription endpoint is `POST https://<your-app-host>/api/feliponetica/word`. It accepts a JSON body containing `text` and an optional `dialect` (`pollito` by default, or `gallo`). The response contains the original `text`, the converted `result`, and `formatted_text`, which places the conversion on the next line after the source.

Configure a long, random `FELIPONETICA_WORD_API_KEY` environment variable on the server before using the endpoint. Requests must send it as a bearer token:

```http
Authorization: Bearer <your-private-api-key>
Content-Type: application/json
```

Example request:

```json
{
  "text": "And, hello!\nHow are you?",
  "dialect": "pollito"
}
```

Punctuation, whitespace, and line breaks are kept in place in `result`; `and` is rendered as `end` (case is preserved). `formatted_text` uses a Windows newline between the source and its conversion for convenient insertion into Word.

Keep the API key out of source control, shared documents, and public macros. Store it only in your private Word integration and the server environment. The endpoint rejects requests if the server key is unset, so it cannot accidentally become public.
