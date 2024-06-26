#include <Parsers/isDiskFunction.h>
#include <Parsers/ASTFunction.h>

namespace DB
{

bool isDiskFunction(ASTPtr ast)
{
    if (!ast)
        return false;

    const auto * function = ast->as<ASTFunction>();
    return function && function->name == "disk" && function->arguments->as<ASTExpressionList>();
}

}
