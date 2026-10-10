"""Simulated-student study: compares our adaptive policy against a random baseline over multiple sessions.
Reports true-mastery gain, learner-model estimation error (MAE) and question repetition rate."""
import json, math, random
import numpy as np
from . import learner as L, assess, db, intake, config as C
from .retrieval import get_index

LR = 0.12  # latent learning rate per practised question (ASSUMPTION - documented in README)


def build_pool(idx, per_topic=40, seed=3):
    rng = random.Random(seed); pool = {}
    for t in L.top_topics():
        units = [u for u in idx.units if u["topic_id"] == t["id"] and len(u["text"].split()) >= 12]
        qs, tries = [], 0
        while len(qs) < per_topic and tries < 8 and units:
            for q in assess.cloze_questions(idx, units, per_topic, rng, topic_units=units):
                if not any(assess.norm(q["stem"]) == assess.norm(x["stem"]) for x in qs): qs.append(q)
            tries += 1
        pool[t["id"]] = qs[:per_topic]
    return pool


def run_arm(policy, pool, tops, pm, profiles, sessions, qps, seed, diag_per_topic=2):
    """Session 0 = diagnostic (same for both arms: new-student cold start). Sessions 1..S use the policy under test."""
    rng = random.Random(seed); tids = [t["id"] for t in tops]; S = sessions + 1
    agg = {"gain": [], "curve": np.zeros(S + 1), "mae": np.zeros(S), "rank": np.zeros(S), "target": np.zeros(S), "mae0": np.zeros(S), "rep": 0, "served": 0}
    for prof in profiles:
        truth = dict(prof["truth"]); est = {t: prof.get("prior_map", {}).get(t, prof["prior"]) for t in tids}; seen = {t: set() for t in tids}; prior0 = dict(est)
        start = np.mean(list(truth.values())); agg["curve"][0] += start

        def ask(t, i):
            qs = pool[t]; rep = i in seen[t]; agg["rep"] += rep; agg["served"] += 1; seen[t].add(i)
            diff = qs[i]["difficulty"]; g = L.GUESS[qs[i]["qtype"]]; sl = L.SLIP[diff]
            m_eff = truth[t] - {"easy": -0.1, "medium": 0.0, "hard": 0.12}[diff]
            pc = g + (1 - g - sl) * min(max(m_eff, 0), 1)
            if rep: pc = max(pc, 0.8)  # memorised answer
            correct = rng.random() < pc; est[t] = L.bkt_update(est[t], correct, g, sl)
            gate = 0.5 + 0.5 * min([truth[p] for p in pm.get(t, [])] or [1.0])  # prerequisites speed learning
            truth[t] += LR * (1 - truth[t]) * gate * (1.3 if not correct else 1.0) * (0.25 if rep else 1.0) * (1.25 if diff == "medium" else 1.0)

        def snapshot(k):
            agg["curve"][k + 1] += np.mean(list(truth.values())); agg["mae"][k] += np.mean([abs(est[t] - truth[t]) for t in tids]); agg["mae0"][k] += np.mean([abs(prior0[t] - truth[t]) for t in tids])
            ra = np.argsort(np.argsort([est[t] for t in tids])); rb = np.argsort(np.argsort([truth[t] for t in tids]))
            agg["rank"][k] += float(np.corrcoef(ra, rb)[0, 1]) if np.std(ra) and np.std(rb) else 0.0  # Spearman

        for t in tids:  # diagnostic
            for _ in range(diag_per_topic):
                if pool[t]:
                    un = [i for i in range(len(pool[t])) if i not in seen[t]]; ask(t, rng.choice(un) if un else 0)
        snapshot(0)
        for s_ in range(1, S):
            alloc = [rng.choice(tids) for _ in range(qps)] if policy == "random" else L.pick_topics(dict(est), pm, qps, rng)
            weakest = set(sorted(tids, key=lambda t: truth[t])[:max(1, len(tids) // 3)])  # truly weakest third, known only to the simulator
            agg["target"][s_] += np.mean([t in weakest for t in alloc]) if alloc else 0.0
            for t in alloc:
                qs = pool[t]
                if not qs: continue
                un = [i for i in range(len(qs)) if i not in seen[t]]
                if policy == "adaptive": i = rng.choice(un) if un else min(seen[t])  # novelty filter
                else: i = rng.randrange(len(qs))  # baseline: no novelty control
                ask(t, i)
            for t in tids: truth[t] = max(0.0, truth[t] - 0.01 * (1 if t not in alloc else 0.3))  # mild forgetting
            snapshot(s_)
        agg["gain"].append(np.mean(list(truth.values())) - start)
    n = len(profiles); r4 = lambda v: [round(float(x / n), 4) for x in v]
    return {"mean_gain": round(float(np.mean(agg["gain"])), 4), "gain_std": round(float(np.std(agg["gain"])), 4),
            "mastery_curve": r4(agg["curve"]), "estimation_mae_by_session": r4(agg["mae"]), "rank_corr_by_session": r4(agg["rank"]), "targeting_by_session": r4(agg["target"])[1:], "prior_only_mae_by_session": r4(agg["mae0"]),
            "repetition_rate": round(agg["rep"] / max(agg["served"], 1), 4), "questions_served": agg["served"], "_gains": [float(g) for g in agg["gain"]]}


def run(n_students=30, sessions=6, qps=12, seed=11, progress=lambda m, p: None):
    idx = get_index(); tops = L.top_topics(); pm = L.prereq_map()
    if not tops: raise ValueError("Upload your course material first (Library tab), then run the study.")
    progress("Building simulation question pool", 0.1); pool = build_pool(idx)
    rng = np.random.default_rng(seed); profiles = []
    for i in range(n_students):
        kind = ["novice", "mixed", "advanced"][i % 3]
        base = {"novice": 0.12, "mixed": 0.35, "advanced": 0.6}[kind]
        truth = {t["id"]: float(np.clip(rng.normal(base, 0.18 if kind == "mixed" else 0.08), 0.02, 0.95)) for t in tops}
        profiles.append({"kind": kind, "truth": truth, "prior": 0.3})  # system starts with NO knowledge of the student
    kind_level = {"novice": "beginner", "mixed": "intermediate", "advanced": "advanced"}
    for pr in profiles:  # intake arm: noisy self-rating -> prior, exactly as intake.apply() does it
        lvl = L.LEVEL_PRIOR[kind_level[pr["kind"]]]; pm_ = {}
        for t, tv in pr["truth"].items():
            noisy = tv + rng.normal(0, 0.2); r_ = "new" if noisy < 0.25 else "good" if noisy > 0.5 else "some"
            pm_[t] = 0.4 * lvl + 0.6 * intake.RATING_PRIOR[r_]
        pr["prior_map"] = pm_
    res = {"pool_size_per_topic": {str(k): len(v) for k, v in pool.items()}, "config": {"students": n_students, "sessions": sessions, "questions_per_session": qps, "profiles": ["novice", "mixed", "advanced"]}}
    flat = [{k: v for k, v in pr.items() if k != "prior_map"} for pr in profiles]
    for k, (name, pol, profs) in enumerate([("adaptive", "adaptive", flat), ("adaptive_intake", "adaptive", profiles), ("random", "random", flat)]):
        progress(f"Simulating: {name}", 0.3 + 0.2 * k); res[name] = run_arm(pol, pool, tops, pm, profs, sessions, qps, seed + (1 if pol == "random" else 0))
    a, c_, b = (np.array(res[x].pop("_gains")) for x in ("adaptive", "adaptive_intake", "random"))
    res["comparison"] = {"gain_improvement_abs": round(float(a.mean() - b.mean()), 4),
                         "gain_improvement_rel_pct": round(float((a.mean() - b.mean()) / max(b.mean(), 1e-9) * 100), 1),
                         "paired_wins_adaptive_pct": round(float(np.mean(a > b) * 100), 1)}
    ad = res["adaptive"]; mae, rk, tg = ad["estimation_mae_by_session"], ad["rank_corr_by_session"], ad["targeting_by_session"]
    res["data_growth"] = {"note": "How personalization changes as the system sees more of a student (adaptive arm, averaged over students). vs_prior_only = how much smaller the learner-model error is than a model that never learns (frozen starting prior); it is the cleanest signal because adaptive practice also changes true mastery, which confounds raw error and rank correlation.",
                          "estimation_mae_first": mae[0], "estimation_mae_last": mae[-1], "estimation_error_reduction_pct": round((1 - mae[-1] / max(mae[0], 1e-9)) * 100, 1),
                          "vs_prior_only_first": round(1 - mae[0] / max(ad["prior_only_mae_by_session"][0], 1e-9), 3), "vs_prior_only_last": round(1 - mae[-1] / max(ad["prior_only_mae_by_session"][-1], 1e-9), 3), "rank_corr_first": rk[0], "rank_corr_last": rk[-1], "targeting_first_session": tg[0], "targeting_last_session": tg[-1],
                          "targeting_random_baseline": res["random"]["targeting_by_session"][-1]}
    res["intake_ablation"] = {"mae_after_diagnostic_without_intake": mae[0], "mae_after_diagnostic_with_intake": res["adaptive_intake"]["estimation_mae_by_session"][0],
                              "mean_gain_without_intake": ad["mean_gain"], "mean_gain_with_intake": res["adaptive_intake"]["mean_gain"],
                              "self_rating_noise_sd": 0.2, "note": "Self-ratings are simulated as truth + Gaussian noise (sd 0.2), then blended with the level prior (40/60) as intake.apply() does."}
    res["assumptions"] = ["Synthetic students: correctness ~ guess/slip model over a latent mastery; learning gain per question is modelled "
                          "(lower for repeated questions, higher with prerequisite mastery). These assumptions favour policies that avoid repeats "
                          "and respect prerequisites, so the results demonstrate the mechanics, not real-world learning gains.",
                          "Pool = offline concept questions generated from your KB (reproducible, no API cost). Baseline = random topic + random question, no novelty filter. Self-ratings in the intake arm are simulated with Gaussian noise."]
    (C.EVAL / "sim_eval.json").write_text(json.dumps(res, indent=1)); progress("Done", 1.0)
    return res
