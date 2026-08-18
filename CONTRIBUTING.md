# Contribuindo

Use Python 3.11 e Node 24 LTS. Crie uma branch curta, mantenha a alteração dentro de um domínio e evite misturar refatoração com mudança de regra financeira.

Antes de abrir um pull request:

```powershell
npm run check
```

Inclua testes para correções e contratos novos. Em cálculos quantitativos, documente unidade, sinal, janela, timezone e comportamento para dados ausentes. Em integrações, documente timeout, retry, rate limit e idempotência.

## Cobertura

O CI usa cobertura incremental: o piso global nunca pode diminuir e deve avançar ate
40%. Fluxos criticos de autenticacao, Funds Flow, opcoes, OCR e persistencia devem
chegar a 60% ou mais. Ao elevar um piso em `ci.yml`, nao o reduza em uma alteracao
posterior para acomodar codigo sem testes.

Cobertura deve vir de comportamento observavel. Priorize calculos financeiros,
contratos HTTP, persistencia, retomada, idempotencia e falhas de provedores. Testes
que apenas importam modulos ou exercitam implementacao privada sem verificar um
resultado de dominio nao justificam aumento do piso.

## Diagnosticos manuais

Checks exploratorios que dependem de provedores, terminais de mercado ou dados
locais pertencem a `scripts/diagnostics`, separados por dominio. Eles nao devem
ser criados na raiz, em `backend/` ou em `backend/scripts`.

Artefatos gerados ficam em `scripts/diagnostics/artifacts` e nao sao versionados.
Credenciais devem vir do ambiente local; nunca declare chaves, tokens ou senhas
nos scripts. Testes automatizados continuam em `backend/tests` e `frontend/tests`.

Na revisão, confirme também que:

- rotas apenas validam e coordenam; regras financeiras permanecem nos serviços;
- clientes externos não vazam respostas, tokens ou stack traces;
- jobs retomáveis persistem o checkpoint somente depois de uma etapa confirmada;
- alterações de payload preservam compatibilidade ou incluem uma migração explícita;
- componentes visuais recebem dados normalizados e não duplicam fórmulas do backend.

Commits não devem conter `.env`, bases, logs, screenshots operacionais ou dados licenciados. Mudanças de schema precisam explicar compatibilidade e estratégia de migração.
