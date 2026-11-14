# Contatos e clientes

**Contatos** é o cadastro de pessoas e organizações, tanto da vida pessoal quanto
profissional. Um contato não é necessariamente um possível comprador. Use grupos
como família, amigos, trabalho e fornecedores; uma pessoa pode estar em vários.

Acrescente a área em **Ajustes → Pastas → Contatos**. O perfil Negócio ou freelancer
já inclui Contatos em cofres novos. Cadastre nome, telefone, e-mail, organização,
grupos, favorito e anotações. A lista permite buscar nome, telefone, e-mail e
organização, filtrar um grupo e mostrar somente favoritos.

## Acompanhamento comercial

**Clientes** é opcional: quem usa o Orquestra para a vida pessoal não precisa
ativá-lo. Ele guarda o acompanhamento comercial, o valor combinado, o próximo
retorno e o histórico. O funil conserva as etapas existentes: contato, proposta,
ativo e encerrado. Aqui, contato e proposta representam possíveis clientes;
ativo representa uma relação comercial em andamento. Não são categorias dos
contatos pessoais.

Na nota de um contato, **Acompanhar em Clientes** cria um registro comercial
vinculado. Se já houver um acompanhamento não arquivado para esse cadastro,
abre o existente. Isso não envia mensagens nem declara uma venda concluída.

Também é possível escolher **Contato vinculado** ao criar ou editar um registro
em Clientes. O telefone e o e-mail são consultados no cadastro original, sem
copiá-los. A nota do contato mostra seus acompanhamentos comerciais.

Uma organização pode ter seu cadastro e seus representantes podem ser contatos
separados, identificados pelo campo Organização. Nesta versão esse campo é texto;
não há uma hierarquia automática de empresas e representantes.

## Cofres existentes e identidade

Nenhum cliente antigo é convertido ou movido automaticamente. Seus campos,
anotações e configurações continuam intactos. Crie o contato e escolha o vínculo
no registro comercial existente. O antigo campo Como falar permanece disponível.

O vínculo usa `contato_id`, um identificador permanente no frontmatter, e resiste
à renomeação do arquivo. Não o edite. Uma cópia criada pelo painel recebe outro
identificador; duplicações externas com o mesmo identificador precisam de revisão
antes de criar novos vínculos. Contatos criados diretamente no Obsidian recebem
um identificador ao usar Acompanhar em Clientes.

Excluir ou arquivar um contato não exclui o histórico do cliente. O vínculo
indisponível fica sinalizado no registro comercial. Restaurar o contato da
lixeira recupera seu identificador e seu vínculo.

O cadastro é local. Esta versão não importa nem sincroniza Google Contatos,
WhatsApp ou listas externas, nem envia mensagens automaticamente.
