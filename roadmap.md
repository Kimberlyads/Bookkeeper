# Roadmap do Bookkeeper

Este é o plano de desenvolvimento do Bookkeeper. Vamos avançar por etapas e validar cada fase antes de considerar o bot pronto.

## 1. Biblioteca confiável — fase atual
- [ ] Conferir a importação do Kindlogger e enriquecer os dados disponíveis
- [ ] Corrigir busca, detalhes e filtros de livros
- [ ] Revisar status de leitura e evitar duplicatas
- [ ] Atualizar os comandos de ajuda

## 2. Progresso de leitura
- [ ] Registrar livro atual, página e percentual
- [ ] Marcar livros como concluídos e registrar datas
- [ ] Histórico, metas e estatísticas

## 3. Diário de leitura
- [ ] Registrar pensamentos e reflexões
- [ ] Vincular registros a livros/capítulos
- [ ] Editar, excluir e consultar registros

## 4. Conversa com IA
- [ ] Perguntas sobre livros e biblioteca
- [ ] Usar contexto das leituras e reflexões
- [ ] Recomendações com cuidado com spoilers e confiabilidade

## 5. Áudio
- [ ] Receber mensagens de voz e transcrever
- [ ] Ditado para o diário
- [ ] Respostas em texto e, futuramente, áudio

## 6. Livros físicos e ISBN
- [ ] Cadastrar por ISBN/código de barras ou imagem
- [ ] Buscar dados bibliográficos e pedir confirmação
- [ ] Distinguir formatos e permitir cadastro manual

## 7. Ofertas e livros gratuitos
- [ ] Consultar preços, promoções e ofertas
- [ ] Filtros por gênero e região (prioridade: Amazon Brasil)
- [ ] Evitar duplicatas e incluir links confiáveis

## 8. Hospedagem contínua (sempre ligado)
- [ ] Escolher uma hospedagem em nuvem adequada
- [ ] Configurar o bot para iniciar automaticamente e funcionar sem o computador ligado
- [ ] Configurar reinicialização em caso de falha e monitoramento por logs
- [ ] Garantir persistência e backups do banco de dados
- [ ] Testar a operação contínua antes de considerar a etapa concluída

## 9. Versão pessoal estável
- [ ] Testes finais, documentação e backups
- [ ] Revisar segurança e tratamento de erros

## 10. Onboarding multiusuário
- [ ] Bibliotecas isoladas e privacidade
- [ ] Importar biblioteca ou começar do zero
- [ ] Testar com usuários beta

## 11. Possibilidades futuras
- [ ] Aplicativo móvel e API
- [ ] Estante visual e leitura de ISBN pela câmera
- [ ] Sincronização entre plataformas

**Princípio:** não lançar uma versão incompleta. Cada etapa será testada antes de avançar.