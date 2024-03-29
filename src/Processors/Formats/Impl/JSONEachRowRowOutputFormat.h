#pragma once

#include <Core/Block.h>
#include <IO/WriteBuffer.h>
#include <Processors/Formats/OutputFormatWithUTF8ValidationAdaptor.h>
#include <Formats/FormatSettings.h>


namespace DB
{

/** The stream for outputting data in JSON format, by object per line.
  */
class JSONEachRowRowOutputFormat : public RowOutputFormatWithUTF8ValidationAdaptor
{
public:
    JSONEachRowRowOutputFormat(
        WriteBuffer & out_,
        const Block & header_,
        const FormatSettings & settings_);

    String getName() const override { return "JSONEachRowRowOutputFormat"; }

    /// Content-Type to set when sending HTTP response.
    String getContentType() const override
    {
        return settings.json.array_of_rows ? "application/json; charset=UTF-8" : "application/x-ndjson; charset=UTF-8" ;
    }

protected:
    void writeField(const IColumn & column, const ISerialization & serialization, size_t row_num) override;
    void writeFieldDelimiter() override;
    void writeRowStartDelimiter() override;
    void writeRowEndDelimiter() override;
    void writeRowBetweenDelimiter() override;
    void writePrefix() override;
    void writeSuffix() override;

    size_t field_number = 0;

private:
    Names fields;

    FormatSettings settings;
};

}
