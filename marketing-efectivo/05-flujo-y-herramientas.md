# 05 · Flujo de trabajo y herramientas

## Calendarios en Notion

| Base de datos | Formato | Plataformas |
|---|---|---|
| Instagram Content Calendar | Carruseles | Instagram, TikTok |
| Instagram Reels Calendar | Reels "How to say" | Instagram, TikTok |
| Facebook Quiz Calendar (dentro de "Instagram Single Photo Calendar") | Quiz HSK de una imagen | Facebook, Instagram (TikTok opcional) |

### Campos comunes

- **Name**: título de la pieza.
- **Topic**: tema en una línea (en reels incluye HSK y número de reel).
- **Status**: `Draft` → `Ready for review` → `Approved` → `Posted` (o `Rejected` / `Failed`).
- **Scheduled date**: fecha de publicación.
- **Platforms**: dónde se publica cuando se aprueba.
- **Caption**: texto completo listo para pegar.
- **TikTok title**: opcional, máximo 90 caracteres.
- **TikTok status** y **TikTok publish id**: los llena solo el poster (`Sent to inbox`, `Posted`, `Failed`; vacío = no enviado).

### Campos por formato

- Carrusel: **Slides** (archivos), **Slide count**.
- Reel: **Video** (1080 × 1920), **Cover**, **Hook** (lo que se ve o se dice en los primeros 3 s), **Script** (clip, voz, consejo de tono, notas), **Audio**, **Duration (s)**.
- Quiz: **Slides** (una imagen), **HSK level**, **Answer** (para el comentario de revelación).

Cuando algo se publica en Instagram, el permalink se pega en el cuerpo de la página de Notion.

## Flujo

1. **Idea → Draft**: se crea la fila con tema, fecha y plataformas.
2. **Producción**: se generan slides, video o imagen y el caption. Parte la hace una rutina en la nube (reels: clip de Veo + voz TTS) y la deja en `Ready for review`.
3. **Revisión humana**: verificar caracteres, pinyin y tonos (en reels, escucharlos), créditos de fotos y caption. Aprobar (`Approved`) o rechazar (`Rejected`).
4. **Publicación**:
   - **Instagram / Facebook**: se publica con el caption de Notion y se pega el permalink.
   - **TikTok**: el poster toma las filas `Approved` con TikTok en Platforms y las manda como borrador al inbox de TikTok de la academia. Una persona agrega el sonido y publica.
5. **Cierre**: `Status` pasa a `Posted`.

## Potochino Poster (TikTok)

Herramienta interna en `tools/tiktok/` del repo del sitio (fuera de GitHub Pages por `_config.yml`).

- `connect.py`: conecta la cuenta de TikTok de la academia (OAuth, permisos `user.info.basic` y `video.upload`), renueva el token (`refresh`) y muestra la cuenta conectada (`whoami`). El access token dura 24 h y el refresh token 365 días.
- `post.py send <slug>`: redimensiona los slides a 1080 px, los sube a `slides/<slug>/` del sitio en un solo commit, espera a que GitHub Pages los sirva y le pide a TikTok que los jale desde el prefijo verificado (`MEDIA_UPLOAD` = borrador en el inbox). Imprime una línea JSON con el resultado.
- `post.py status <publish_id>`: consulta el estado de un envío.
- El *slug* de cada carrusel es el ID de la página de Notion (ej. `p-401072cc19008191abaac7ea2359348b`).
- Si TikTok rota el refresh token, el script avisa con `REFRESH_TOKEN_ROTATED` y hay que guardar el nuevo valor. El token vive en una página privada de Notion; **nunca se copia a documentos ni repositorios**.

## Sitio web (GitHub Pages)

- https://albertoromo203-lab.github.io: página principal, Términos de servicio y Política de privacidad (requisitos de la app de TikTok).
- `slides/`: solo carruseles aprobados y listos para ser públicos, para que TikTok los descargue de una URL verificada.
- Archivos `tiktok*.txt`: verificación de dominio de TikTok Developers. No borrar.
