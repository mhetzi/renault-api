actions/charge-schedule
'''''''''''''''''''''''

.. rst-class:: endpoint

Base url:
   ``/commerce/v1/accounts/{account_id}/kamereon/kca/car-adapter/v2/cars/{vin}/actions/charge-schedule``

For vehicles using KCM EV settings, ``RenaultVehicle.set_ev_programs``
reads and updates the complete ``/kcm/v1/vehicles/{vin}/ev/settings`` resource.
Each supplied ``KcmEvProgram`` represents one departure program. Existing
program types are kept when ``program_type`` is omitted, unrelated EV settings
are preserved, and unused program slots are deactivated. The number of
available slots is taken from the server response. For example:

.. code:: python

   from renault_api.kamereon.models import KcmEvProgram

   program = KcmEvProgram(
       raw_data={},
       departure_time="06:45",
       days=["monday", "tuesday"],
   )
   await vehicle.set_ev_programs([program])

Sample payload:
   Sample payload is not yet available for this endpoint.

   Please check the `Contributor Guide`_ to provide a sample.

.. _Contributor Guide: contributing.html
