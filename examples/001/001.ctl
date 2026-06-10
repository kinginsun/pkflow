;; 1. Based on:
;; 2. Description: 2-comp IV, linear elimination — pkflow example 001
;; 3. Label:
;; x1. Author:

$PROBLEM PK demo

$INPUT ID TIME DV AMT CMT MDV EVID WT CRCL AGE SEX CENT

$DATA demo.csv IGNORE=@

$SUBROUTINES ADVAN3 TRANS4

$PK
CL = THETA(1) * EXP(ETA(1))
V1 = THETA(2) * EXP(ETA(2))
Q  = THETA(3) * EXP(ETA(3))
V2 = THETA(4)
S1 = V1

$ERROR
IPRED = F
W = SQRT(THETA(5)**2*IPRED**2 + THETA(6)**2)
Y = IPRED + W*EPS(1)
IRES  = DV-IPRED
IWRES = IRES/W

$THETA
(0, 5)   ; CL
(0, 30)  ; V1
(0, 2)   ; Q
(0, 50)  ; V2
(0, .1)  ; Prop.RE (sd)
(0, .5)  ; Add.RE (sd)

$OMEGA
(0.1) ; IIV CL
(0.1) ; IIV V1
(0.1) ; IIV Q

$SIGMA
1 FIX ; proportional error carried in $ERROR

$EST METHOD=1 INTER MAXEVAL=2000 NOABORT SIG=3 PRINT=1 POSTHOC
$COV

; Xpose-style diagnostics tables
$TABLE ID TIME DV MDV EVID PRED IPRED CWRES IWRES ONEHEADER NOPRINT FILE=sdtab1
$TABLE ID CL V1 V2 Q WT CRCL AGE SEX ONEHEADER NOPRINT FIRSTONLY FILE=patab1
