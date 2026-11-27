# Atualizar o Orquestra

Clique no ícone de atualização para sincronizar o aplicativo com a versão oficial
e reabrir o painel. A ação começa no clique, sem confirmação adicional. A página
recarrega quando confirma a revisão nova. Salve as edições abertas antes de atualizar.

A sincronização substitui as alterações locais nos arquivos do aplicativo e não
cria cópias ZIP, stashes ou pastas duplicadas. Arquivos extras sem conflito ficam
no lugar. As notas, configurações e temas do vault não são alterados. Se um vault
ocupar um caminho usado pelo aplicativo, a operação é cancelada para protegê-lo.
Commits próprios que divirjam da main oficial também não são descartados.

O ícone aparece quando há uma revisão nova ou arquivos locais diferentes dos que
estão em uso. A consulta à main ocorre ao abrir a página e a cada 30 minutos;
sem conexão, o uso do painel continua disponível. A instalação exige acesso direto
por localhost, Git e uv instalados e a main do repositório oficial. Pelo Tailscale,
o ícone orienta abrir localhost no computador.

O painel continua aberto enquanto o código e as dependências são preparados.
No Windows, a preparação evita substituir o executável em uso. Depois, o painel
retoma no mesmo vault e porta. Se houver falha, o aviso informa o problema;
use `uv run --frozen orquestra` na pasta do aplicativo para reabrir se necessário.

O comando `uv run --frozen orquestra atualizar` usa a mesma sincronização.

## Instalações antigas no Windows

> **Antes de confirmar:** o recuperador baixa o atualizador oficial mais recente.
> Mesmo que um `.cmd` baixado anteriormente prometa criar um ZIP, a sincronização
> atual não cria backup e substitui alterações locais nos arquivos do aplicativo.
> Se quiser conservar alguma personalização, cancele e faça uma cópia da pasta do
> aplicativo em um local fora do aplicativo e do vault. Confira a cópia antes de
> rodar a atualização.

Se uma versão antiga impedir a atualização por alterações locais, use
[Atualizar Orquestra.cmd](../scripts/Atualizar%20Orquestra.cmd), disponível pelo
botão **Download raw file** no GitHub. Abra-o, escolha a pasta do aplicativo
(onde ficam `pyproject.toml` e `uv.lock`) e confirme. O arquivo baixa o atualizador
oficial e executa a mesma sincronização. Depois, recarregue o painel.
