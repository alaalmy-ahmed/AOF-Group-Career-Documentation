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


--
-- Name: training; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA training;


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
    missed_tasks integer,
    branch character varying(255)
);


--
-- Name: branches; Type: TABLE; Schema: training; Owner: -
--

CREATE TABLE training.branches (
    code character varying(30),
    name character varying(255)
);


--
-- Name: issues; Type: TABLE; Schema: training; Owner: -
--

CREATE TABLE training.issues (
    date date,
    branch character varying(255),
    meal character varying(50),
    description character varying(50),
    manager character varying(50)
);


--
-- Name: tasks; Type: TABLE; Schema: training; Owner: -
--

CREATE TABLE training.tasks (
    date date,
    meal character varying(50),
    done_tasks integer,
    branch_missed character varying(255),
    due_time character varying(50),
    missed_tasks integer
);


--
-- PostgreSQL database dump complete
--

