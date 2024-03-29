#pragma once

#include <Interpreters/IInterpreter.h>
#include <Parsers/IAST_fwd.h>


namespace DB
{

class ASTCreateConnectionQuery;
struct AWSConnection;

class InterpreterCreateConnectionQuery : public IInterpreter, WithMutableContext
{
public:
    InterpreterCreateConnectionQuery(const ASTPtr & query_ptr_, ContextMutablePtr context_) : WithMutableContext(context_), query_ptr(query_ptr_) {}

    BlockIO execute() override;

    static void updateConnectionFromQuery(AWSConnection & connection, const ASTCreateConnectionQuery & query);

private:
    ASTPtr query_ptr;
};

}
