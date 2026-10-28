"""Writes evals/cases/g*.json (40 synthetic golden cases). The 10 hand-made cases stay as they are.

    uv run python -m evals.make_golden

All names, companies, IDs and contacts are invented; `.example` domains never resolve.
"""

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).parent / "cases"

# (id, country, region, language, case_type, urgent, user_text, expected_facts)
CASES: list[tuple[str, str, str | None, str, str, bool, str, dict[str, str]]] = [
    # --- refund_refused --------------------------------------------------------------
    (
        "g01-pk-fridge",
        "PK",
        "PK-PB",
        "en",
        "refund_refused",
        False,
        "I'm Bilal Ahmed from Lahore. Bought a fridge from CoolHome Appliances on 2026-06-12, "
        "invoice CH-20931, for 98,500 rupees. The compressor died in 3 weeks. They refuse to "
        "replace it. I want a replacement. Their email: care@coolhome.example",
        {
            "buyer_name": "Bilal Ahmed",
            "seller_name": "CoolHome Appliances",
            "seller_contact": "care@coolhome.example",
            "order_id": "CH-20931",
            "order_date": "2026-06-12",
            "amount": "98500",
            "currency": "PKR",
            "remedy_wanted": "replacement",
        },
    ),
    (
        "g02-pk-ur-mobile",
        "PK",
        "PK-SD",
        "ur",
        "refund_refused",
        False,
        "میرا نام عمران خان ہے، کراچی سے۔ میں نے 2026-08-03 کو PhoneZone سے موبائل خریدا، آرڈر "
        "PZ-5512، قیمت 54000 روپے۔ موبائل کی بیٹری خراب نکلی۔ وہ واپس نہیں لے رہے۔ مجھے پیسے واپس "
        "چاہئیں۔ ای میل: help@phonezone.example",
        {
            "buyer_name": "عمران خان",
            "seller_name": "PhoneZone",
            "seller_contact": "help@phonezone.example",
            "order_id": "PZ-5512",
            "order_date": "2026-08-03",
            "amount": "54000",
            "currency": "PKR",
        },
    ),
    (
        "g03-pk-ur-ac",
        "PK",
        "PK-IS",
        "ur",
        "refund_refused",
        False,
        "میں زینب علی ہوں۔ 2026-05-20 کو AirCool Traders سے اے سی لیا، رسید نمبر AC-0098، "
        "120000 روپے۔ اے سی ٹھنڈا نہیں کرتا۔ دکاندار مرمت سے انکار کر رہا ہے۔ مجھے نیا اے سی "
        "چاہیے۔ رابطہ: sales@aircool.example",
        {
            "buyer_name": "زینب علی",
            "seller_name": "AirCool Traders",
            "seller_contact": "sales@aircool.example",
            "order_id": "AC-0098",
            "order_date": "2026-05-20",
            "amount": "120000",
            "currency": "PKR",
        },
    ),
    (
        "g04-in-laptop",
        "IN",
        "IN-KA",
        "en",
        "refund_refused",
        False,
        "Rahul Verma here, Bengaluru. Ordered a laptop from TechBazaar on 2026-07-15 (order "
        "TB-778812), paid Rs 62,990. It won't charge. Seller refuses refund saying it's physical "
        "damage, which is false. I want a full refund. Contact: support@techbazaar.example",
        {
            "buyer_name": "Rahul Verma",
            "seller_name": "TechBazaar",
            "seller_contact": "support@techbazaar.example",
            "order_id": "TB-778812",
            "order_date": "2026-07-15",
            "amount": "62990",
            "currency": "INR",
            "remedy_wanted": "full refund",
        },
    ),
    (
        "g05-in-sofa",
        "IN",
        "IN-DL",
        "en",
        "refund_refused",
        False,
        "My name is Anjali Mehta, Delhi. FurniCraft delivered a sofa on 2026-04-02 against order "
        "FC-1209. I paid 45,000 INR. The frame cracked in a month. They ignore my calls. I want a "
        "replacement sofa. Email orders@furnicraft.example",
        {
            "buyer_name": "Anjali Mehta",
            "seller_name": "FurniCraft",
            "seller_contact": "orders@furnicraft.example",
            "order_id": "FC-1209",
            "amount": "45000",
            "currency": "INR",
            "remedy_wanted": "replacement",
        },
    ),
    (
        "g06-gb-boots",
        "GB",
        None,
        "en",
        "refund_refused",
        False,
        "Hi, I'm Emma Clarke. I bought walking boots from TrailGear UK on 2026-09-05, order "
        "TG-44120, £129.00. The sole came off after two walks. They say it's wear and tear. I want "
        "my money back. Their email is help@trailgear.example",
        {
            "buyer_name": "Emma Clarke",
            "seller_name": "TrailGear UK",
            "seller_contact": "help@trailgear.example",
            "order_id": "TG-44120",
            "order_date": "2026-09-05",
            "amount": "129",
            "currency": "GBP",
            "remedy_wanted": "money back",
        },
    ),
    (
        "g07-gb-tv",
        "GB",
        None,
        "en",
        "refund_refused",
        False,
        "Oliver Smith. Ordered a TV from BrightVision on 2 March 2026, order number BV-30017, "
        "paid £499.99. Dead pixels from day one. They want me to pay for return postage and then "
        "a repair. I want a replacement TV. orders@brightvision.example",
        {
            "buyer_name": "Oliver Smith",
            "seller_name": "BrightVision",
            "seller_contact": "orders@brightvision.example",
            "order_id": "BV-30017",
            "order_date": "2026-03-02",
            "amount": "499.99",
            "currency": "GBP",
            "remedy_wanted": "replacement",
        },
    ),
    (
        "g08-us-blender",
        "US",
        "US-NY",
        "en",
        "refund_refused",
        False,
        "I'm James Carter in New York. I bought a blender from KitchenPro on 2026-08-20, order "
        "KP-99021, $89.99. The motor smells of burning. They refuse returns after 14 days. I want "
        "a refund. Email: returns@kitchenpro.example",
        {
            "buyer_name": "James Carter",
            "seller_name": "KitchenPro",
            "seller_contact": "returns@kitchenpro.example",
            "order_id": "KP-99021",
            "order_date": "2026-08-20",
            "amount": "89.99",
            "currency": "USD",
            "remedy_wanted": "refund",
        },
    ),
    (
        "g09-us-bike",
        "US",
        "US-WA",
        "en",
        "refund_refused",
        False,
        "Sarah Nguyen, Seattle. Bought an e-bike from VoltRide on June 1, 2026, order VR-2026-551 "
        "for $1,450. The battery stopped holding charge. They keep 'escalating' with no answer. I "
        "want a replacement battery. support@voltride.example",
        {
            "buyer_name": "Sarah Nguyen",
            "seller_name": "VoltRide",
            "seller_contact": "support@voltride.example",
            "order_id": "VR-2026-551",
            "order_date": "2026-06-01",
            "amount": "1450",
            "currency": "USD",
        },
    ),
    (
        "g10-es-movil",
        "ES",
        None,
        "es",
        "refund_refused",
        False,
        "Soy Carlos Ruiz, de Madrid. Compré un móvil en MóvilYa el 2026-05-11, pedido MY-30812, "
        "por 349 EUR. La pantalla parpadea. Se niegan a cambiarlo. Quiero un reembolso. Correo: "
        "soporte@movilya.example",
        {
            "buyer_name": "Carlos Ruiz",
            "seller_name": "MóvilYa",
            "seller_contact": "soporte@movilya.example",
            "order_id": "MY-30812",
            "order_date": "2026-05-11",
            "amount": "349",
            "currency": "EUR",
        },
    ),
    (
        "g11-es-colchon",
        "ES",
        None,
        "es",
        "refund_refused",
        False,
        "Me llamo Ana Torres. El 2026-02-27 compré un colchón en DescansoPlus (pedido DP-1180), "
        "pagué 520 EUR. Se hundió en dos semanas. No responden. Quiero que me devuelvan el dinero. "
        "Contacto: clientes@descansoplus.example",
        {
            "buyer_name": "Ana Torres",
            "seller_name": "DescansoPlus",
            "seller_contact": "clientes@descansoplus.example",
            "order_id": "DP-1180",
            "order_date": "2026-02-27",
            "amount": "520",
            "currency": "EUR",
        },
    ),
    (
        "g12-fr-aspirateur",
        "FR",
        None,
        "fr",
        "refund_refused",
        False,
        "Je m'appelle Julien Martin. J'ai acheté un aspirateur chez MaisonTech le 2026-03-18, "
        "commande MT-66310, pour 199 EUR. Il ne s'allume plus. Le vendeur refuse le remboursement. "
        "Je veux être remboursé. E-mail : service@maisontech.example",
        {
            "buyer_name": "Julien Martin",
            "seller_name": "MaisonTech",
            "seller_contact": "service@maisontech.example",
            "order_id": "MT-66310",
            "order_date": "2026-03-18",
            "amount": "199",
            "currency": "EUR",
        },
    ),
    (
        "g13-fr-velo",
        "FR",
        None,
        "fr",
        "refund_refused",
        False,
        "Bonjour, je suis Camille Dubois. Le 2026-06-30 j'ai commandé un vélo chez CycloShop "
        "(commande CS-2041) pour 640 EUR. Le cadre est fissuré. Ils ne répondent pas. Je demande "
        "un remplacement. Contact : aide@cycloshop.example",
        {
            "buyer_name": "Camille Dubois",
            "seller_name": "CycloShop",
            "seller_contact": "aide@cycloshop.example",
            "order_id": "CS-2041",
            "order_date": "2026-06-30",
            "amount": "640",
            "currency": "EUR",
        },
    ),
    (
        "g14-br-geladeira",
        "BR",
        "BR-SP",
        "pt",
        "refund_refused",
        False,
        "Meu nome é Pedro Almeida, de São Paulo. Comprei uma geladeira na CasaFria em 2026-07-08, "
        "pedido CF-90011, por 3.200 BRL. Ela não gela. A loja se recusa a trocar. Quero o "
        "reembolso. E-mail: atendimento@casafria.example",
        {
            "buyer_name": "Pedro Almeida",
            "seller_name": "CasaFria",
            "seller_contact": "atendimento@casafria.example",
            "order_id": "CF-90011",
            "order_date": "2026-07-08",
            "amount": "3200",
            "currency": "BRL",
        },
    ),
    (
        "g15-br-celular",
        "BR",
        "BR-RJ",
        "pt",
        "refund_refused",
        False,
        "Sou Mariana Costa, do Rio. Em 2026-04-14 comprei um celular na FoneMax, pedido FM-7781, "
        "1.899 BRL. Veio com a câmera quebrada. Não aceitam devolução. Quero a troca. Contato: "
        "suporte@fonemax.example",
        {
            "buyer_name": "Mariana Costa",
            "seller_name": "FoneMax",
            "seller_contact": "suporte@fonemax.example",
            "order_id": "FM-7781",
            "order_date": "2026-04-14",
            "amount": "1899",
            "currency": "BRL",
        },
    ),
    (
        "g16-de-kaffee",
        "DE",
        None,
        "de",
        "refund_refused",
        False,
        "Ich heiße Lukas Becker. Am 2026-01-22 habe ich bei KaffeeWelt eine Kaffeemaschine "
        "gekauft, Bestellung KW-5530, für 279 EUR. Sie leckt. Der Händler lehnt die Erstattung ab. "
        "Ich möchte mein Geld zurück. E-Mail: kundendienst@kaffeewelt.example",
        {
            "buyer_name": "Lukas Becker",
            "seller_name": "KaffeeWelt",
            "seller_contact": "kundendienst@kaffeewelt.example",
            "order_id": "KW-5530",
            "order_date": "2026-01-22",
            "amount": "279",
            "currency": "EUR",
        },
    ),
    (
        "g17-ng-generator",
        "NG",
        "NG-LA",
        "en",
        "refund_refused",
        False,
        "My name is Chinedu Okafor, Lagos. I bought a generator from PowerHub on 2026-03-09, "
        "receipt PH-4410, for 450,000 naira. It stopped after 2 days. They won't refund or fix it. "
        "I want my money refunded. sales@powerhub.example",
        {
            "buyer_name": "Chinedu Okafor",
            "seller_name": "PowerHub",
            "seller_contact": "sales@powerhub.example",
            "order_id": "PH-4410",
            "order_date": "2026-03-09",
            "amount": "450000",
            "currency": "NGN",
            "remedy_wanted": "refund",
        },
    ),
    (
        "g18-ke-phone",
        "KE",
        None,
        "en",
        "refund_refused",
        False,
        "I am Grace Wanjiru from Nairobi. On 2026-05-02 I bought a phone from SimuStore, order "
        "SS-1203, KES 23,500. It keeps restarting. They refuse to exchange it. I want an exchange. "
        "help@simustore.example",
        {
            "buyer_name": "Grace Wanjiru",
            "seller_name": "SimuStore",
            "seller_contact": "help@simustore.example",
            "order_id": "SS-1203",
            "order_date": "2026-05-02",
            "amount": "23500",
            "currency": "KES",
            "remedy_wanted": "exchange",
        },
    ),
    (
        "g19-ae-watch",
        "AE",
        None,
        "en",
        "refund_refused",
        False,
        "Fatima Al Mansoori, Dubai. Bought a smartwatch from GadgetsME on 2026-09-21, order "
        "GM-80022, AED 899. The strap broke and the screen fogs. They refuse a refund. I want a "
        "full refund. support@gadgetsme.example",
        {
            "buyer_name": "Fatima Al Mansoori",
            "seller_name": "GadgetsME",
            "seller_contact": "support@gadgetsme.example",
            "order_id": "GM-80022",
            "order_date": "2026-09-21",
            "amount": "899",
            "currency": "AED",
            "remedy_wanted": "full refund",
        },
    ),
    (
        "g20-ca-jacket",
        "CA",
        "CA-ON",
        "en",
        "refund_refused",
        False,
        "Liam Tremblay, Toronto. Ordered a winter jacket from NorthWear on 2026-10-04, order "
        "NW-33019, CAD 260. The zipper broke on day one. They will only offer store credit. I want "
        "a refund to my card. care@northwear.example",
        {
            "buyer_name": "Liam Tremblay",
            "seller_name": "NorthWear",
            "seller_contact": "care@northwear.example",
            "order_id": "NW-33019",
            "order_date": "2026-10-04",
            "amount": "260",
            "currency": "CAD",
            "remedy_wanted": "refund",
        },
    ),
    # --- subscription_cancel ---------------------------------------------------------
    (
        "g21-gb-broadband",
        "GB",
        None,
        "en",
        "subscription_cancel",
        False,
        "I'm Sophie Turner. I cancelled my FastNet broadband (account FN-118842) by phone and "
        "email on 2026-07-31, but they still take £34.50 every month. I want it cancelled and the "
        "August and September payments refunded. Email: billing@fastnet.example",
        {
            "buyer_name": "Sophie Turner",
            "company_name": "FastNet",
            "company_contact": "billing@fastnet.example",
            "account_id": "FN-118842",
            "cancel_requested_on": "2026-07-31",
            "amount": "34.50",
            "currency": "GBP",
        },
    ),
    (
        "g22-us-gym",
        "US",
        "US-TX",
        "en",
        "subscription_cancel",
        False,
        "Daniel Brooks, Austin. PowerGym won't cancel my membership, member ID PG-55031. I sent "
        "a cancellation letter on 2026-06-15. They keep charging $49.99. I want the membership "
        "cancelled and a refund of charges since June. members@powergym.example",
        {
            "buyer_name": "Daniel Brooks",
            "company_name": "PowerGym",
            "company_contact": "members@powergym.example",
            "account_id": "PG-55031",
            "cancel_requested_on": "2026-06-15",
            "amount": "49.99",
            "currency": "USD",
        },
    ),
    (
        "g23-in-ott",
        "IN",
        "IN-TN",
        "en",
        "subscription_cancel",
        False,
        "Karthik S, Chennai. I asked CineStream to cancel my plan (user ID CS-IN-90412) on "
        "2026-08-01 but they auto-renewed and took 1,499 rupees. I want a refund and cancellation. "
        "help@cinestream.example",
        {
            "buyer_name": "Karthik S",
            "company_name": "CineStream",
            "company_contact": "help@cinestream.example",
            "account_id": "CS-IN-90412",
            "cancel_requested_on": "2026-08-01",
            "amount": "1499",
            "currency": "INR",
        },
    ),
    (
        "g24-pk-internet",
        "PK",
        "PK-PB",
        "en",
        "subscription_cancel",
        False,
        "Ayesha Siddiqui here, Lahore. I asked NetLink to disconnect my internet (customer number "
        "NL-77310) on 2026-05-05. They are still billing Rs 4,500 monthly. I want it disconnected "
        "and the extra bills cancelled. Email complaints@netlink.example",
        {
            "buyer_name": "Ayesha Siddiqui",
            "company_name": "NetLink",
            "company_contact": "complaints@netlink.example",
            "account_id": "NL-77310",
            "cancel_requested_on": "2026-05-05",
            "amount": "4500",
            "currency": "PKR",
        },
    ),
    (
        "g25-es-gimnasio",
        "ES",
        None,
        "es",
        "subscription_cancel",
        False,
        "Soy Laura Gómez. Pedí la baja de mi gimnasio FitClub (socio FC-2207) el 2026-04-30 y "
        "siguen cobrándome 39,90 EUR al mes. Quiero la baja y que me devuelvan los cobros. Correo: "
        "socios@fitclub.example",
        {
            "buyer_name": "Laura Gómez",
            "company_name": "FitClub",
            "company_contact": "socios@fitclub.example",
            "account_id": "FC-2207",
            "cancel_requested_on": "2026-04-30",
            "currency": "EUR",
        },
    ),
    (
        "g26-fr-box",
        "FR",
        None,
        "fr",
        "subscription_cancel",
        False,
        "Je suis Thomas Petit. J'ai résilié mon abonnement BoxPlus (client BP-50981) le "
        "2026-03-01, mais ils prélèvent encore 29,99 EUR par mois. Je veux la résiliation et le "
        "remboursement. Contact : resiliation@boxplus.example",
        {
            "buyer_name": "Thomas Petit",
            "company_name": "BoxPlus",
            "company_contact": "resiliation@boxplus.example",
            "account_id": "BP-50981",
            "cancel_requested_on": "2026-03-01",
            "currency": "EUR",
        },
    ),
    (
        "g27-br-streaming",
        "BR",
        "BR-MG",
        "pt",
        "subscription_cancel",
        False,
        "Sou Rafael Souza. Cancelei a assinatura da TocaFilmes (conta TF-31207) em 2026-06-10, "
        "mas continuam cobrando 39,90 BRL. Quero o cancelamento e o estorno. E-mail: "
        "ajuda@tocafilmes.example",
        {
            "buyer_name": "Rafael Souza",
            "company_name": "TocaFilmes",
            "company_contact": "ajuda@tocafilmes.example",
            "account_id": "TF-31207",
            "cancel_requested_on": "2026-06-10",
            "currency": "BRL",
        },
    ),
    (
        "g28-de-handy",
        "DE",
        None,
        "de",
        "subscription_cancel",
        False,
        "Ich bin Anna Schmidt. Ich habe meinen Handyvertrag bei FunkPlus (Kundennummer FP-88120) "
        "am 2026-02-14 gekündigt. Sie buchen weiter 24,99 EUR ab. Ich will die Kündigung "
        "bestätigt und das Geld zurück. E-Mail: vertrag@funkplus.example",
        {
            "buyer_name": "Anna Schmidt",
            "company_name": "FunkPlus",
            "company_contact": "vertrag@funkplus.example",
            "account_id": "FP-88120",
            "cancel_requested_on": "2026-02-14",
            "currency": "EUR",
        },
    ),
    (
        "g29-us-software",
        "US",
        "US-IL",
        "en",
        "subscription_cancel",
        False,
        "Michael Reed, Chicago. I cancelled my PhotoSuite Pro subscription (account PS-4471-MR) "
        "on 2026-01-10. They charged me $29.99 in February and March anyway. I want those charges "
        "refunded. billing@photosuite.example",
        {
            "buyer_name": "Michael Reed",
            "company_name": "PhotoSuite Pro",
            "company_contact": "billing@photosuite.example",
            "account_id": "PS-4471-MR",
            "cancel_requested_on": "2026-01-10",
            "amount": "29.99",
            "currency": "USD",
        },
    ),
    (
        "g30-ke-tv",
        "KE",
        None,
        "en",
        "subscription_cancel",
        False,
        "Peter Otieno, Nairobi. I asked SkyBox TV to stop my package, smartcard SB-60918, on "
        "2026-07-01. They still deduct KES 1,800 monthly. I want it stopped and refunded. "
        "care@skybox.example",
        {
            "buyer_name": "Peter Otieno",
            "company_name": "SkyBox TV",
            "company_contact": "care@skybox.example",
            "account_id": "SB-60918",
            "cancel_requested_on": "2026-07-01",
            "amount": "1800",
            "currency": "KES",
        },
    ),
    # --- scam ------------------------------------------------------------------------
    (
        "g31-in-upi",
        "IN",
        "IN-MH",
        "en",
        "scam",
        True,
        "I am Sneha Patil. Today 2026-10-28 a caller said my electricity would be cut and made "
        "me pay Rs 12,000 by UPI to settle a bill. Transaction ID UPI-55102. My bank is "
        "Deccan Bank. I think it was a scam.",
        {
            "buyer_name": "Sneha Patil",
            "amount": "12000",
            "currency": "INR",
            "paid_on": "2026-10-28",
            "payment_method": "UPI",
            "bank_name": "Deccan Bank",
            "transaction_id": "UPI-55102",
        },
    ),
    (
        "g32-gb-romance",
        "GB",
        None,
        "en",
        "scam",
        False,
        "My name is Margaret Hill. Over three months someone I met online asked for money. The "
        "last payment was £3,000 by bank transfer on 2026-05-19 from Albion Bank. He has now "
        "vanished.",
        {
            "buyer_name": "Margaret Hill",
            "amount": "3000",
            "currency": "GBP",
            "paid_on": "2026-05-19",
            "payment_method": "bank transfer",
            "bank_name": "Albion Bank",
        },
    ),
    (
        "g33-us-crypto",
        "US",
        "US-FL",
        "en",
        "scam",
        False,
        "Kevin Price, Miami. An 'investment' site called CoinPeak took $8,500 I sent by wire on "
        "2026-04-03 from Gulf Coast Bank. They won't let me withdraw anything.",
        {
            "buyer_name": "Kevin Price",
            "amount": "8500",
            "currency": "USD",
            "paid_on": "2026-04-03",
            "payment_method": "wire",
            "bank_name": "Gulf Coast Bank",
            "scammer_name": "CoinPeak",
        },
    ),
    (
        "g34-pk-ur-jazz",
        "PK",
        "PK-SD",
        "ur",
        "scam",
        True,
        "میرا نام حمزہ رشید ہے۔ آج 2026-10-28 کو ایک شخص نے انعام کا جھانسہ دے کر مجھ سے 25000 "
        "روپے موبائل والٹ سے منگوا لیے، ٹرانزیکشن آئی ڈی TX-99120۔ میرا بینک Indus Bank ہے۔",
        {
            "buyer_name": "حمزہ رشید",
            "amount": "25000",
            "currency": "PKR",
            "paid_on": "2026-10-28",
            "transaction_id": "TX-99120",
            "bank_name": "Indus Bank",
        },
    ),
    (
        "g35-es-falso-banco",
        "ES",
        None,
        "es",
        "scam",
        True,
        "Me llamo Javier Moreno. Ayer, 2026-10-27, me llamaron haciéndose pasar por mi banco, "
        "BancoSol, y transferí 2.000 EUR a una cuenta 'segura'. Referencia TR-44019.",
        {
            "buyer_name": "Javier Moreno",
            "amount": "2000",
            "currency": "EUR",
            "paid_on": "2026-10-27",
            "bank_name": "BancoSol",
            "transaction_id": "TR-44019",
        },
    ),
    (
        "g36-fr-colis",
        "FR",
        None,
        "fr",
        "scam",
        False,
        "Je suis Nathalie Bernard. Le 2026-09-12 j'ai payé 1,99 EUR de 'frais de douane' sur un "
        "faux site de livraison, puis 780 EUR ont été débités de ma carte. Ma banque est Banque "
        "Lumière.",
        {
            "buyer_name": "Nathalie Bernard",
            "currency": "EUR",
            "paid_on": "2026-09-12",
            "bank_name": "Banque Lumière",
        },
    ),
    (
        "g37-br-pix",
        "BR",
        "BR-SP",
        "pt",
        "scam",
        True,
        "Sou Lucas Ferreira. Hoje, 2026-10-28, paguei 1.500 BRL por Pix a um vendedor falso de "
        "um celular. Comprovante PIX-77302. Meu banco é Banco Aurora.",
        {
            "buyer_name": "Lucas Ferreira",
            "amount": "1500",
            "currency": "BRL",
            "paid_on": "2026-10-28",
            "payment_method": "Pix",
            "transaction_id": "PIX-77302",
            "bank_name": "Banco Aurora",
        },
    ),
    (
        "g38-ng-job",
        "NG",
        "NG-FC",
        "en",
        "scam",
        False,
        "I'm Aisha Bello, Abuja. A fake recruiter asked me to pay a 'processing fee' of 150,000 "
        "naira by transfer on 2026-08-30 from Savannah Bank. The job does not exist.",
        {
            "buyer_name": "Aisha Bello",
            "amount": "150000",
            "currency": "NGN",
            "paid_on": "2026-08-30",
            "payment_method": "transfer",
            "bank_name": "Savannah Bank",
        },
    ),
    (
        "g39-ca-tax",
        "CA",
        "CA-BC",
        "en",
        "scam",
        False,
        "Emily Chen, Vancouver. A caller claiming to be from the tax agency made me buy CAD 1,200 "
        "in gift cards on 2026-07-22 and read him the codes.",
        {
            "buyer_name": "Emily Chen",
            "amount": "1200",
            "currency": "CAD",
            "paid_on": "2026-07-22",
            "payment_method": "gift cards",
        },
    ),
    (
        "g40-de-shop",
        "DE",
        None,
        "de",
        "scam",
        False,
        "Ich bin Jonas Wolf. Am 2026-09-03 habe ich in einem Fake-Shop Schuhe für 180 EUR per "
        "Überweisung bezahlt, Referenz FS-2290. Nichts kam an, der Shop ist weg. Meine Bank ist "
        "Nordbank.",
        {
            "buyer_name": "Jonas Wolf",
            "amount": "180",
            "currency": "EUR",
            "paid_on": "2026-09-03",
            "transaction_id": "FS-2290",
            "bank_name": "Nordbank",
        },
    ),
]


def build() -> list[dict[str, Any]]:
    out = []
    for cid, country, region, lang, ctype, urgent, text, facts in CASES:
        out.append(
            {
                "id": cid,
                "country": country,
                "region": region,
                "language": lang,
                "case_type": ctype,
                "urgent": urgent,
                "user_text": text,
                "evidence": [],
                "expected_facts": facts,
            }
        )
    return out


def main() -> None:
    for case in build():
        (OUT / f"{case['id']}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"wrote {len(CASES)} cases to {OUT}")


if __name__ == "__main__":
    main()
