# Segurança

## Credenciais

Não abra issue nem commit com chaves, tokens, senhas, cookies ou URLs assinadas. Use `.env` local ou o secret store do ambiente. `.env.example` contém somente placeholders.

Não tente tornar uma chave publicada segura por ofuscação, Base64 ou remoção em um commit posterior. Revogue a credencial no provedor, gere outra e remova o valor de todo o histórico antes de publicar.

Antes de publicar este repositório pela primeira vez:

1. revogue todas as chaves que já apareceram em conversas, terminais, screenshots ou arquivos temporários;
2. gere credenciais novas com o menor escopo possível;
3. execute uma varredura de segredos no diretório e no histórico Git;
4. confirme que bancos, logs, capturas e exports não estão staged;
5. proteja a branch principal e habilite secret scanning no GitHub.

## Autenticação e autorização

- mantenha `AQUILES_AUTH_ENABLED=True` fora de testes isolados;
- use `scripts/create_auth_user.py` para gerar hashes de senha;
- conceda `viewer` para leitura, `operator` para comandos e `admin` somente para administração;
- use o mesmo `AQUILES_AUTH_TOKEN_SECRET` em todos os microserviços;
- rotacione o segredo de assinatura para invalidar imediatamente todos os tokens ativos;
- nunca coloque `AQUILES_AUTH_USERS_JSON` ou o segredo de assinatura no repositório.

Depois de inicializar o Git e antes do primeiro push, confirme que nenhum arquivo sensível está rastreado:

```powershell
git status --short --ignored
git ls-files | Select-String -Pattern '\.env|\.pem$|\.key$|\.p12$|\.pfx$|credentials|secrets'
```

O segundo comando deve listar, no máximo, `.env.example` e documentação deliberadamente pública.

## Reporte de vulnerabilidade

Envie o relato de forma privada ao mantenedor, incluindo componente, impacto, reprodução mínima e mitigação sugerida. Não inclua dados reais de mercado ou credenciais.

## Princípios

- falhas 5xx não retornam traceback;
- timeouts e limites são obrigatórios em integrações externas;
- entradas externas são tratadas como não confiáveis;
- dependências são auditadas no CI;
- logs usam identificadores de correlação e evitam conteúdo sensível.
