create table rp_documents (
    document_id varchar2(64) primary key,
    source_path varchar2(2048) not null,
    file_name varchar2(512) not null,
    file_type varchar2(32) not null,
    checksum varchar2(128) not null,
    title varchar2(512) not null,
    status varchar2(32) default 'indexed' not null,
    language_tags clob,
    metadata clob,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    constraint rp_documents_lang_json check (language_tags is json),
    constraint rp_documents_meta_json check (metadata is json)
);

create table rp_chunks (
    chunk_id varchar2(64) primary key,
    document_id varchar2(64) not null references rp_documents(document_id) on delete cascade,
    source_path varchar2(2048) not null,
    file_type varchar2(32) not null,
    chunk_type varchar2(64) not null,
    title varchar2(512) not null,
    section_path clob,
    chunk_index number not null,
    display_text clob not null,
    embedding_text clob not null,
    language_tags clob,
    citation_anchor clob,
    parser_used varchar2(128),
    parser_confidence number,
    metadata clob,
    image_refs clob,
    created_at timestamp default current_timestamp,
    constraint rp_chunks_section_json check (section_path is json),
    constraint rp_chunks_lang_json check (language_tags is json),
    constraint rp_chunks_citation_json check (citation_anchor is json),
    constraint rp_chunks_meta_json check (metadata is json),
    constraint rp_chunks_image_refs_json check (image_refs is json)
);

create unique index rp_chunks_doc_idx on rp_chunks(document_id, chunk_index);

create table rp_embeddings (
    chunk_id varchar2(64) primary key references rp_chunks(chunk_id) on delete cascade,
    document_id varchar2(64) not null references rp_documents(document_id) on delete cascade,
    model_id varchar2(256) not null,
    embedding vector(1024, float32) not null,
    created_at timestamp default current_timestamp
);

create table rp_images (
    image_id varchar2(64) primary key,
    document_id varchar2(64) not null references rp_documents(document_id) on delete cascade,
    source_path varchar2(2048) not null,
    image_path varchar2(2048) not null,
    title varchar2(512) not null,
    caption_text clob,
    related_section_path clob,
    related_chunk_id varchar2(64),
    language_tags clob,
    citation_anchor clob,
    metadata clob,
    created_at timestamp default current_timestamp,
    constraint rp_images_section_json check (related_section_path is json),
    constraint rp_images_lang_json check (language_tags is json),
    constraint rp_images_citation_json check (citation_anchor is json),
    constraint rp_images_meta_json check (metadata is json)
);

create unique index rp_images_path_idx on rp_images(image_path);

create table rp_image_embeddings (
    image_id varchar2(64) primary key references rp_images(image_id) on delete cascade,
    document_id varchar2(64) not null references rp_documents(document_id) on delete cascade,
    model_id varchar2(256) not null,
    embedding vector(1024, float32) not null,
    created_at timestamp default current_timestamp
);

create table rp_ingest_jobs (
    job_id number generated always as identity primary key,
    document_id varchar2(64),
    job_type varchar2(64) not null,
    status varchar2(32) not null,
    stats clob,
    error_message clob,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    constraint rp_ingest_jobs_stats_json check (stats is json)
);

create table rp_query_log (
    query_id number generated always as identity primary key,
    query_text clob not null,
    request_payload clob,
    response_payload clob,
    created_at timestamp default current_timestamp,
    constraint rp_query_log_request_json check (request_payload is json),
    constraint rp_query_log_response_json check (response_payload is json)
);
