import { useEffect, useState } from "react";

import {
  getPersonIntelligence,
  getPhoneIntelligence,
  getAccountIntelligence,

  startDigiLockerVerification,
  mockDigiLockerVerification,

  getPersonIdentityComparison,
  apiError,
} from "../api";


/* =========================================================
   SMALL UI COMPONENTS
   ========================================================= */

function Badge({ children, tone = "" }) {
  return (
    <span className={`badge ${tone}`}>
      {children}
    </span>
  );
}


function Explain({
  title = "Why NETRA says this",
  children,
}) {
  return (
    <div className="xai-box">
      <div className="xai-title">
        ◈ {title}
      </div>

      <div className="muted">
        {children}
      </div>
    </div>
  );
}


function KV({ label, value }) {
  return (
    <div className="kv">
      <span>{label}</span>

      <strong>
        {value ?? "—"}
      </strong>
    </div>
  );
}


function Section({ title, children }) {
  return (
    <div className="entity-section">
      <h3>{title}</h3>
      {children}
    </div>
  );
}


function List({ rows, label }) {
  return (
    <div className="stack">
      {(rows || []).map((row, index) => (
        <div
          className="item"
          key={index}
        >
          {label(row)}
        </div>
      ))}

      {!rows?.length && (
        <div className="muted">
          No records.
        </div>
      )}
    </div>
  );
}


/* =========================================================
   STATUS HELPERS
   ========================================================= */

function statusTone(status) {
  const value = String(status || "").toUpperCase();

  if (
    value.includes("VERIFIED") ||
    value === "MATCH"
  ) {
    return "ok";
  }

  if (
    value.includes("MISMATCH") ||
    value === "REJECTED" ||
    value === "FAILED"
  ) {
    return "bad";
  }

  return "warn";
}


function percentage(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return null;
  }

  let number = Number(value);

  /*
   * NETRA normally uses confidence values
   * between 0 and 1.
   *
   * This also safely handles 0-100 values.
   */
  if (number > 1) {
    number = number / 100;
  }

  return Math.max(
    0,
    Math.min(100, number * 100)
  );
}


/* =========================================================
   DIGILOCKER VERIFICATION RESULT
   ========================================================= */

function DigiLockerVerification({ result }) {
  if (!result) {
    return null;
  }

  /*
   * Identity-comparison endpoint returns:
   *
   * {
   *   verified,
   *   status,
   *   confidence,
   *   police_evidence,
   *   government_evidence,
   *   field_comparison,
   *   explainable_ai
   * }
   *
   * Mock verification can additionally contain:
   *
   * {
   *   verification_id,
   *   verification_status,
   *   verification_confidence,
   *   verified_name,
   *   source,
   *   ...
   * }
   */

  const comparison =
    result.comparison || null;

  const rawVerification =
    result.verification || result;

  const status =
    comparison?.status ||
    rawVerification?.verification_status ||
    rawVerification?.status ||
    "NOT_VERIFIED";

  const confidence =
    comparison?.confidence ??
    rawVerification?.verification_confidence ??
    rawVerification?.confidence ??
    0;

  const verifiedName =
    comparison?.government_evidence?.name ||
    rawVerification?.verified_name ||
    rawVerification?.full_name ||
    null;

  const source =
    comparison?.government_evidence?.source ||
    rawVerification?.source ||
    "DigiLocker";

  const verifiedAt =
    comparison?.government_evidence?.verified_at ||
    rawVerification?.verified_at ||
    null;

  const consentValidTill =
    comparison?.government_evidence?.consent_valid_till ||
    rawVerification?.consent_valid_till ||
    null;

  const scope =
    comparison?.government_evidence?.scope ||
    rawVerification?.scope ||
    null;

  const fieldComparison =
    comparison?.field_comparison ||
    result.field_comparison ||
    [];

  const xai =
    comparison?.explainable_ai ||
    result.explainable_ai ||
    null;

  const confidencePercent =
    percentage(confidence);

  return (
    <div className="verification-card">

      {/* =====================================================
          HEADER
          ===================================================== */}

      <div className="panel-head">

        <h3>
          DigiLocker Identity Verification
        </h3>

        <Badge tone={statusTone(status)}>
          {status}
        </Badge>

      </div>


      {/* =====================================================
          GOVERNMENT IDENTITY
          ===================================================== */}

      <div className="item">

        <div
          className="muted"
          style={{
            marginBottom: "6px",
          }}
        >
          Government-verified name
        </div>

        <div
          style={{
            fontWeight: 700,
            fontSize: "16px",
          }}
        >
          {verifiedName || "Name unavailable"}
        </div>

      </div>


      {/* =====================================================
          CONFIDENCE
          ===================================================== */}

      <div className="confidence">

        Identity confidence:

        <strong>
          {confidencePercent === null
            ? "—"
            : `${confidencePercent.toFixed(1)}%`}
        </strong>

      </div>


      {/* =====================================================
          VERIFICATION METADATA
          ===================================================== */}

      <Section title="Verification details">

        <div className="stack">

          <div className="item">

            <span className="muted">
              Source
            </span>

            <div>
              {source || "—"}
            </div>

          </div>


          {verifiedAt && (
            <div className="item">

              <span className="muted">
                Verified at
              </span>

              <div>
                {new Date(
                  verifiedAt
                ).toLocaleString()}
              </div>

            </div>
          )}


          {consentValidTill && (
            <div className="item">

              <span className="muted">
                Consent valid till
              </span>

              <div>
                {consentValidTill}
              </div>

            </div>
          )}


          {scope && (
            <div className="item">

              <span className="muted">
                Access scope
              </span>

              <div>
                {scope}
              </div>

            </div>
          )}


          {rawVerification?.verification_id && (
            <div className="item">

              <span className="muted">
                Verification ID
              </span>

              <div>
                {rawVerification.verification_id}
              </div>

            </div>
          )}


          {rawVerification?.name_similarity !==
            null &&
            rawVerification?.name_similarity !==
              undefined && (

              <div className="item">

                <span className="muted">
                  Name similarity
                </span>

                <div>
                  {
                    percentage(
                      rawVerification.name_similarity
                    )?.toFixed(1)
                  }
                  %
                </div>

              </div>

            )}

        </div>

      </Section>


      {/* =====================================================
          FIELD-BY-FIELD COMPARISON
          ===================================================== */}

      {fieldComparison.length > 0 && (

        <Section title="Field-by-field comparison">

          <div className="stack">

            {fieldComparison.map(
              (field, index) => {

                const fieldName =
                  field.field ||
                  field.name ||
                  `Field ${index + 1}`;

                const fieldStatus =
                  field.status ||
                  (
                    field.match === true
                      ? "MATCH"
                      : field.match === false
                        ? "MISMATCH"
                        : "REVIEW"
                  );

                const policeValue =
                  field.police_value ??
                  field.police ??
                  field.source_value ??
                  null;

                const governmentValue =
                  field.government_value ??
                  field.government ??
                  field.verified_value ??
                  null;

                return (
                  <div
                    className="item"
                    key={`${fieldName}-${index}`}
                  >

                    <div className="match-row">

                      <span>
                        {fieldName}
                      </span>

                      <Badge
                        tone={statusTone(
                          fieldStatus
                        )}
                      >
                        {fieldStatus}
                      </Badge>

                    </div>


                    {policeValue !== null && (
                      <div className="muted">
                        Police evidence:{" "}
                        <strong>
                          {String(policeValue)}
                        </strong>
                      </div>
                    )}


                    {governmentValue !== null && (
                      <div className="muted">
                        Government evidence:{" "}
                        <strong>
                          {String(
                            governmentValue
                          )}
                        </strong>
                      </div>
                    )}


                    {field.reason && (
                      <small>
                        {field.reason}
                      </small>
                    )}

                  </div>
                );
              }
            )}

          </div>

        </Section>

      )}


      {/* =====================================================
          POLICE EVIDENCE
          ===================================================== */}

      {comparison?.police_evidence && (

        <Section title="Police-collected identity">

          <div className="stack">

            {comparison.police_evidence.name && (
              <div className="item">

                <span className="muted">
                  Name
                </span>

                <div>
                  {comparison.police_evidence.name}
                </div>

              </div>
            )}


            {comparison.police_evidence.person_id && (
              <div className="item">

                <span className="muted">
                  Person ID
                </span>

                <div>
                  {comparison.police_evidence.person_id}
                </div>

              </div>
            )}


            {comparison.police_evidence.case_id && (
              <div className="item">

                <span className="muted">
                  Case ID
                </span>

                <div>
                  {comparison.police_evidence.case_id}
                </div>

              </div>
            )}

          </div>

        </Section>

      )}


      {/* =====================================================
          EXPLAINABLE AI
          ===================================================== */}

      {xai && (

        <Explain
          title="Explainable verification"
        >

          {xai.summary && (
            <div
              style={{
                marginBottom: "8px",
              }}
            >
              <strong>
                {xai.summary}
              </strong>
            </div>
          )}


          {Array.isArray(xai.reasons) &&
            xai.reasons.length > 0 && (

              <div className="stack">

                {xai.reasons.map(
                  (reason, index) => (
                    <div
                      key={index}
                    >
                      • {reason}
                    </div>
                  )
                )}

              </div>

            )}


          {xai.decision && (

            <div
              style={{
                marginTop: "8px",
              }}
            >
              Decision:

              <strong>
                {" "}
                {xai.decision}
              </strong>
            </div>

          )}

        </Explain>

      )}


      {/* =====================================================
          VERIFICATION NOTE
          ===================================================== */}

      {rawVerification?.verification_note && (

        <Explain
          title="Verification note"
        >
          {rawVerification.verification_note}
        </Explain>

      )}


      {/* =====================================================
          IMPORTANT LIMITATION
          ===================================================== */}

      <Explain
        title="Important limitation"
      >
        DigiLocker verification is a government
        identity signal. It should be interpreted
        together with the underlying police evidence,
        graph relationships and other independent
        evidence.

        {" "}

        A phone number, bank account or graph
        relationship by itself is not government
        identity proof.
      </Explain>

    </div>
  );
}


/* =========================================================
   MAIN COMPONENT
   ========================================================= */

export default function EntityIntelligencePanel({
  caseId,
  selection,
  onOpenHypotheses,
}) {

  const [data, setData] =
    useState(null);

  const [verification, setVerification] =
    useState(null);

  const [loading, setLoading] =
    useState(false);

  const [verifying, setVerifying] =
    useState(false);

  const [error, setError] =
    useState(null);


  const type =
    selection?.type;

  const id =
    selection?.entityId;


  /* =======================================================
     LOAD ENTITY INTELLIGENCE
     ======================================================= */

  useEffect(() => {

    if (
      !caseId ||
      !type ||
      id === null ||
      id === undefined
    ) {
      setData(null);
      setVerification(null);
      setError(null);
      return;
    }


    let cancelled = false;

    setLoading(true);
    setError(null);
    setVerification(null);


    let request;


    if (type === "PERSON") {

      request =
        getPersonIntelligence(
          caseId,
          id
        );

    } else if (type === "PHONE") {

      request =
        getPhoneIntelligence(
          caseId,
          id
        );

    } else if (type === "ACCOUNT") {

      request =
        getAccountIntelligence(
          caseId,
          id
        );

    } else {

      setError(
        `Unsupported entity type: ${type}`
      );

      setLoading(false);

      return;
    }


    request
      .then((result) => {

        if (!cancelled) {
          setData(result);
        }

      })
      .catch((err) => {

        if (!cancelled) {
          setError(
            apiError(err)
          );
        }

      })
      .finally(() => {

        if (!cancelled) {
          setLoading(false);
        }

      });


    return () => {
      cancelled = true;
    };

  }, [
    caseId,
    type,
    id,
  ]);


  /* =======================================================
     RESOLVE PERSON FROM SELECTED ENTITY
     ======================================================= */

  function getResolvedPersonId() {

    /* PERSON */

    if (type === "PERSON") {

      return (
        data?.person?.PersonID ??
        id
      );
    }


    /* PHONE */

    if (type === "PHONE") {

      return (
        data?.persons?.[0]?.PersonID ??
        data?.people?.[0]?.PersonID ??
        data?.selected_case_people?.[0]?.PersonID ??
        null
      );
    }


    /* ACCOUNT */

    if (type === "ACCOUNT") {

      return (
        data?.person?.PersonID ??
        null
      );
    }


    return null;
  }


  function getResolvedPersonName() {

    if (type === "PERSON") {

      return (
        data?.person?.FullName ||
        `PERSON:${id}`
      );
    }


    if (type === "PHONE") {

      return (
        data?.persons?.[0]?.FullName ||
        data?.people?.[0]?.FullName ||
        data?.selected_case_people?.[0]?.FullName ||
        "Associated person"
      );
    }


    if (type === "ACCOUNT") {

      return (
        data?.person?.FullName ||
        "Linked person"
      );
    }


    return null;
  }


  /* =======================================================
     DIGILOCKER VERIFICATION
     ======================================================= */

  async function verifyWithDigiLocker() {

    const personId =
      getResolvedPersonId();


    if (
      personId === null ||
      personId === undefined
    ) {

      setError(
        "NETRA could not resolve this entity to a PERSON. DigiLocker verification cannot start."
      );

      return;
    }


    setVerifying(true);
    setError(null);


    try {

      /*
       * STEP 1
       *
       * Start the EXISTING DigiLocker flow.
       */

      const start =
        await startDigiLockerVerification(
          caseId,
          personId
        );


      /* ===================================================
         MOCK MODE
         =================================================== */

      if (
        start?.mode === "mock"
      ) {

        /*
         * Run the existing synthetic verification.
         */

        const mock =
          await mockDigiLockerVerification(
            caseId,
            personId
          );


        /*
         * Fetch the richer comparison result.
         */

        const comparison =
          await getPersonIdentityComparison(
            caseId,
            personId
          );


        setVerification({
          ...mock,
          comparison,
        });


        setVerifying(false);

        return;
      }


      /* ===================================================
         REAL DIGILOCKER MODE
         =================================================== */

      if (
        start?.mode === "production" &&
        start?.authorization_url
      ) {

        const handleMessage =
          async (event) => {

            /*
             * Successful DigiLocker callback.
             */

            if (
              event.data?.type ===
              "DIGILOCKER_SUCCESS"
            ) {

              try {

                /*
                 * Get authoritative stored
                 * comparison from NETRA backend.
                 */

                const comparison =
                  await getPersonIdentityComparison(
                    caseId,
                    personId
                  );


                setVerification({
                  ...(event.data.result || {}),
                  comparison,
                });


                setError(null);

              } catch (err) {

                setError(
                  apiError(err)
                );

              } finally {

                setVerifying(false);

                window.removeEventListener(
                  "message",
                  handleMessage
                );

              }

            }


            /*
             * Failed/denied DigiLocker callback.
             */

            if (
              event.data?.type ===
              "DIGILOCKER_ERROR"
            ) {

              setError(
                event.data.description ||
                "DigiLocker authorization failed."
              );


              setVerifying(false);


              window.removeEventListener(
                "message",
                handleMessage
              );

            }

          };


        window.addEventListener(
          "message",
          handleMessage
        );


        const popup =
          window.open(
            start.authorization_url,
            "digilocker",
            [
              "width=600",
              "height=800",
              "resizable=yes",
              "scrollbars=yes",
            ].join(",")
          );


        if (!popup) {

          window.removeEventListener(
            "message",
            handleMessage
          );


          setError(
            "Popup was blocked. Please allow popups for NETRA."
          );


          setVerifying(false);
        }


        /*
         * Do NOT set verifying=false here.
         *
         * The OAuth callback will do it after
         * DigiLocker sends the result.
         */

        return;
      }


      throw new Error(
        "DigiLocker did not return a valid authorization response."
      );

    } catch (err) {

      console.error(
        "DigiLocker verification failed:",
        err
      );


      setError(
        apiError(err)
      );


      setVerifying(false);
    }
  }


  /* =======================================================
     NO ENTITY SELECTED
     ======================================================= */

  if (!selection) {

    return (
      <article className="panel-card">

        <h2>
          Entity Intelligence
        </h2>

        <div className="muted">
          Select a PERSON, PHONE or ACCOUNT
          node in the graph.
        </div>

      </article>
    );
  }


  /* =======================================================
     LOADING
     ======================================================= */

  if (loading) {

    return (
      <article className="panel-card">

        <h2>
          Entity Intelligence
        </h2>

        <div className="muted">
          Loading evidence…
        </div>

      </article>
    );
  }


  /* =======================================================
     ERROR BEFORE DATA
     ======================================================= */

  if (error && !data) {

    return (
      <article className="panel-card">

        <h2>
          Entity Intelligence
        </h2>

        <div className="error-text">
          {error}
        </div>

      </article>
    );
  }


  /* =======================================================
     PERSON
     ======================================================= */

  if (type === "PERSON") {

    const person =
      data?.person || {};


    return (
      <article
        className="panel-card entity-panel"
      >

        {/* -------------------------------------------------
            HEADER
           ------------------------------------------------- */}

        <div className="panel-head">

          <h2>
            {person.FullName ||
              `PERSON:${id}`}
          </h2>

          <Badge>
            PERSON
          </Badge>

        </div>


        {/* -------------------------------------------------
            BASIC INFORMATION
           ------------------------------------------------- */}

        <div className="kv-grid">

          <KV
            label="Person ID"
            value={
              person.PersonID
            }
          />

          <KV
            label="Role"
            value={
              person.SourceRole
            }
          />

          <KV
            label="Case"
            value={
              person.CrimeNo
            }
          />

          <KV
            label="Place signal"
            value={
              person.DistrictName ||
              person.UnitName
            }
          />

        </div>


        {/* -------------------------------------------------
            ASSOCIATED EVIDENCE
           ------------------------------------------------- */}

        <Section
          title="Associated evidence"
        >

          <List
            rows={data?.phones}
            label={(x) =>
              `PHONE · ${x.PhoneNumber}`
            }
          />


          <List
            rows={data?.accounts}
            label={(x) =>
              `ACCOUNT · ${x.BankName} · ${x.AccountNumber}`
            }
          />


          <List
            rows={data?.vehicles}
            label={(x) =>
              `VEHICLE · ${x.RegistrationNumber}`
            }
          />

        </Section>


        {/* -------------------------------------------------
            XAI ASSOCIATION
           ------------------------------------------------- */}

        {data?.xai?.association_signal && (

          <Explain>

            <b>
              {
                data.xai
                  .association_signal
                  .level
              }
            </b>{" "}

            association.

            {" "}

            {
              data.xai
                .association_signal
                .explanation
            }

            {" "}

            Method:

            {" "}

            {data.xai.method}

          </Explain>

        )}


        {/* -------------------------------------------------
            DIGILOCKER
           ------------------------------------------------- */}

        <button
          className="primary-btn"
          onClick={
            verifyWithDigiLocker
          }
          disabled={verifying}
        >

          {verifying
            ? "Verifying with DigiLocker…"
            : "Verify with DigiLocker"}

        </button>


        {error && (
          <div className="error-inline">
            {error}
          </div>
        )}


        {verification && (
          <DigiLockerVerification
            result={verification}
          />
        )}


        {/* -------------------------------------------------
            HYPOTHESES
           ------------------------------------------------- */}

        <button
          className="secondary-btn"
          onClick={() =>
            onOpenHypotheses?.(
              person.PersonID
            )
          }
        >
          Open hypotheses →
        </button>

      </article>
    );
  }


  /* =======================================================
     PHONE
     ======================================================= */

  if (type === "PHONE") {

    const phone =
      data?.phone || {};


    /*
     * Different backend versions may expose
     * associated persons under different names.
     *
     * Support all current shapes.
     */

    const persons =
      data?.persons ||
      data?.people ||
      data?.selected_case_people ||
      [];


    const resolvedPerson =
      persons[0] || null;


    return (
      <article
        className="panel-card entity-panel"
      >

        {/* -------------------------------------------------
            HEADER
           ------------------------------------------------- */}

        <div className="panel-head">

          <h2>
            {phone.PhoneNumber ||
              data?.phone_number ||
              `PHONE:${id}`}
          </h2>

          <Badge>
            PHONE
          </Badge>

        </div>


        {/* -------------------------------------------------
            PHONE INFORMATION
           ------------------------------------------------- */}

        <div className="kv-grid">

          <KV
            label="Phone ID"
            value={
              phone.PhoneID ??
              id
            }
          />

          <KV
            label="Phone number"
            value={
              phone.PhoneNumber ||
              data?.phone_number
            }
          />

          <KV
            label="Primary"
            value={
              phone.IsPrimary === 1
                ? "Yes"
                : phone.IsPrimary === 0
                  ? "No"
                  : "—"
            }
          />

        </div>


        {/* -------------------------------------------------
            PERSON RESOLUTION
           ------------------------------------------------- */}

        <Section
          title="Resolved person"
        >

          {resolvedPerson ? (

            <div className="item">

              <strong>
                {resolvedPerson.FullName}
              </strong>

              <div className="muted">

                PERSON:

                {" "}

                {resolvedPerson.PersonID}

              </div>

            </div>

          ) : (

            <div className="muted">
              No person could be resolved
              from this phone.
            </div>

          )}

        </Section>


        {/* -------------------------------------------------
            RELATED ACCOUNTS
           ------------------------------------------------- */}

        <Section
          title="Related accounts"
        >

          <List
            rows={data?.accounts}
            label={(x) =>
              `${x.BankName} · ${x.AccountNumber}`
            }
          />

        </Section>


        {/* -------------------------------------------------
            RELATED VEHICLES
           ------------------------------------------------- */}

        <Section
          title="Related vehicles"
        >

          <List
            rows={data?.vehicles}
            label={(x) =>
              x.RegistrationNumber
            }
          />

        </Section>


        {/* -------------------------------------------------
            COMMUNICATIONS
           ------------------------------------------------- */}

        {data?.communications?.length > 0 && (

          <Section
            title="Communications"
          >

            <List
              rows={
                data.communications.slice(
                  0,
                  8
                )
              }
              label={(x) =>
                `${x.CallDateTime || x.datetime || "—"} · ${
                  x.DurationSeconds ??
                  x.duration ??
                  "—"
                } sec`
              }
            />

          </Section>

        )}


        {/* -------------------------------------------------
            LOCATION SIGNALS
           ------------------------------------------------- */}

        {data?.locations?.length > 0 && (

          <Section
            title="Location signals"
          >

            <List
              rows={
                data.locations.slice(
                  0,
                  8
                )
              }
              label={(x) =>
                `${x.DistrictName || x.LocationName || x.TowerName || "Location"}`
              }
            />

          </Section>

        )}


        {/* -------------------------------------------------
            XAI
           ------------------------------------------------- */}

        {data?.xai?.association_signal && (

          <Explain>

            <b>
              {
                data.xai
                  .association_signal
                  .level
              }
            </b>{" "}

            phone association.

            {" "}

            {
              data.xai
                .association_signal
                .explanation
            }

            {" "}

            {data.xai.identity_warning}

          </Explain>

        )}


        {/* -------------------------------------------------
            IDENTITY RESOLUTION EXPLANATION
           ------------------------------------------------- */}

        <Explain
          title="Identity resolution path"
        >

          NETRA first resolves the selected
          phone entity to its associated PERSON
          record.

          {" "}

          DigiLocker verification is then
          performed against that PERSON, not
          against the phone number itself.

        </Explain>


        {/* -------------------------------------------------
            DIGILOCKER BUTTON
           ------------------------------------------------- */}

        <button
          className="primary-btn"
          disabled={
            !resolvedPerson ||
            verifying
          }
          onClick={
            verifyWithDigiLocker
          }
        >

          {verifying
            ? "Verifying with DigiLocker…"
            : "Verify resolved person with DigiLocker"}

        </button>


        {error && (
          <div className="error-inline">
            {error}
          </div>
        )}


        {verification && (
          <DigiLockerVerification
            result={verification}
          />
        )}

      </article>
    );
  }


  /* =======================================================
     ACCOUNT
     ======================================================= */

  if (type === "ACCOUNT") {

    const account =
      data?.account || {};


    const linkedPerson =
      data?.person || null;


    return (
      <article
        className="panel-card entity-panel"
      >

        {/* -------------------------------------------------
            HEADER
           ------------------------------------------------- */}

        <div className="panel-head">

          <h2>

            {account.BankName ||
              "Bank Account"}

            {" · "}

            {account.AccountNumber ||
              `ACCOUNT:${id}`}

          </h2>

          <Badge>
            ACCOUNT
          </Badge>

        </div>


        {/* -------------------------------------------------
            ACCOUNT / PERSON INFORMATION
           ------------------------------------------------- */}

        <div className="kv-grid">

          <KV
            label="Account ID"
            value={
              account.AccountID ??
              id
            }
          />

          <KV
            label="Person"
            value={
              linkedPerson?.FullName
            }
          />

          <KV
            label="Person ID"
            value={
              linkedPerson?.PersonID
            }
          />

          <KV
            label="Place signal"
            value={
              linkedPerson?.DistrictName ||
              linkedPerson?.UnitName
            }
          />

        </div>


        {/* -------------------------------------------------
            TRANSACTIONS
           ------------------------------------------------- */}

        <Section
          title="Transactions"
        >

          <List
            rows={
              (
                data?.transactions ||
                []
              ).slice(0, 8)
            }
            label={(x) =>
              `${x.TxnDateTime || "—"} · ₹${
                x.Amount ?? "—"
              } · ${
                x.TxnType ||
                "TRANSACTION"
              }`
            }
          />

        </Section>


        {/* -------------------------------------------------
            RELATED VEHICLES
           ------------------------------------------------- */}

        {data?.vehicles?.length > 0 && (

          <Section
            title="Related vehicles"
          >

            <List
              rows={data.vehicles}
              label={(x) =>
                x.RegistrationNumber
              }
            />

          </Section>

        )}


        {/* -------------------------------------------------
            XAI
           ------------------------------------------------- */}

        {data?.xai?.association_signal && (

          <Explain>

            <b>
              {
                data.xai
                  .association_signal
                  .level
              }
            </b>{" "}

            account association.

            {" "}

            {
              data.xai
                .association_signal
                .explanation
            }

            {" "}

            {data.xai.identity_warning}

          </Explain>

        )}


        {/* -------------------------------------------------
            IDENTITY RESOLUTION
           ------------------------------------------------- */}

        <Explain
          title="Identity resolution path"
        >

          NETRA first resolves the bank account
          to its linked PERSON record.

          {" "}

          DigiLocker verification is then
          performed against that PERSON.

          {" "}

          The bank account itself is not treated
          as government identity proof.

        </Explain>


        {/* -------------------------------------------------
            DIGILOCKER
           ------------------------------------------------- */}

        <button
          className="primary-btn"
          disabled={
            !linkedPerson ||
            verifying
          }
          onClick={
            verifyWithDigiLocker
          }
        >

          {verifying
            ? "Verifying with DigiLocker…"
            : "Verify linked person with DigiLocker"}

        </button>


        {error && (
          <div className="error-inline">
            {error}
          </div>
        )}


        {verification && (
          <DigiLockerVerification
            result={verification}
          />
        )}

      </article>
    );
  }


  /* =======================================================
     UNSUPPORTED ENTITY
     ======================================================= */

  return (
    <article className="panel-card">

      <h2>
        Entity Intelligence
      </h2>

      <div className="error-text">
        Unsupported entity type:
        {" "}
        {type}
      </div>

    </article>
  );
}