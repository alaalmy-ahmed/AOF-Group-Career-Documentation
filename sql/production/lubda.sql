--
-- PostgreSQL database dump
--

-- Dumped from database version 16.3
-- Dumped by pg_dump version 16.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: operation; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA operation;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: issues; Type: TABLE; Schema: operation; Owner: -
--

CREATE TABLE operation.issues (
    date date,
    project character varying(255),
    branch character varying(255),
    problem character varying(255),
    manager character varying(255),
    notes text
);


--
-- Name: tasks; Type: TABLE; Schema: operation; Owner: -
--

CREATE TABLE operation.tasks (
    date date,
    project character varying(255),
    done_tasks integer,
    branch_missed character varying(255)
);


--
-- PostgreSQL database dump complete
--

